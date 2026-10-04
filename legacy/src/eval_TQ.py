import json
import re
import time
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Tuple, Any, Callable, Optional
import numpy as np
from scipy import stats
from concurrent.futures import ThreadPoolExecutor, as_completed
import functools
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import extract_answer_from_response, eva_video_list
from gpt_request import request_gemini_with_video, request_gemini
from prompts import get_unlearning_and_video_learning_prompt, get_unlearning_prompt


def retry(max_retries=3, base_delay=0.5, jitter=0.2):
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            delay = base_delay
            while True:
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    attempt += 1
                    if attempt > max_retries:
                        raise
                    time.sleep(delay + random.uniform(0, jitter))
                    delay *= 2

        return wrapper

    return deco


@dataclass
class Question:
    """Educational question with multiple choice options"""

    question: str
    options: List[str]
    correct_answer: str
    difficulty: str = "medium"


@dataclass
class EvaluationResult:
    """Results from SKU evaluation"""

    concept: str
    pre_unlearning_score: float
    post_unlearning_score: float
    post_video_score: float
    unlearning_success: bool
    learning_gain: float
    detailed_responses: Dict[str, Any]


def load_questions_from_json(json_path: str) -> Dict[str, List[Question]]:
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    concept_questions: Dict[str, List[Question]] = {}
    for concept, qlist in raw.items():
        qs: List[Question] = []
        for q in qlist:
            # Normalize option order to A-D
            options_dict = q.get("options", {})
            ordered_keys = ["A", "B", "C", "D"]
            options = [options_dict[k] for k in ordered_keys if k in options_dict]
            # Convert correct answer from letter to text to match grading logic
            ans_letter = q.get("answer", "").strip().upper()
            if ans_letter not in ["A", "B", "C", "D"]:
                # Skip and log if error occurs instead of raising
                print(
                    f"[WARN] Invalid answer letter '{ans_letter}' for concept '{concept}' question '{q.get('question','')[:40]}...'"
                )
                continue
            ans_idx = ord(ans_letter) - ord("A")
            if ans_idx >= len(options):
                print(f"[WARN] Answer index out of range for concept '{concept}'")
                continue

            qs.append(
                Question(
                    question=q.get("question", ""),
                    options=options,
                    correct_answer=options[ans_idx],
                    difficulty=q.get("difficulty", "medium"),
                )
            )
        if qs:
            concept_questions[concept] = qs
    return concept_questions


@retry(max_retries=3, base_delay=0.6, jitter=0.3)
def _call_text_api(prompt: str) -> str:
    response = request_gemini(prompt=prompt)
    return extract_answer_from_response(response)


@retry(max_retries=3, base_delay=0.6, jitter=0.3)
def _call_video_api(prompt: str, video_path: str) -> str:
    response = request_gemini_with_video(prompt=prompt, video_path=video_path)
    return extract_answer_from_response(response)


def make_mllm_api(video_path: Optional[str]) -> Callable[[str], str]:
    if video_path:
        return lambda prompt: _call_video_api(prompt, video_path)
    else:
        return lambda prompt: _call_text_api(prompt)


class SelectiveKnowledgeUnlearning:
    def __init__(self, mllm_api_function, per_question_workers: int = 4):
        self.mllm_api = mllm_api_function
        # Concurrency within each individual concept at each stage (at the problem level)
        self.per_question_workers = max(1, per_question_workers)

    def _format_mcq_prompt_block(self, i: int, q: Question) -> str:
        opts = "\n".join([f"{chr(65+j)}) {opt}" for j, opt in enumerate(q.options)])
        return f"Question {i}: {q.question}\nOptions:\n{opts}\n"

    def _grade_batch(self, questions: List[Question], responses: List[str]) -> Tuple[float, List[str]]:
        correct = 0
        detailed = []
        for q, resp in zip(questions, responses):
            detailed.append(resp)
            m = re.search(r"\b[A-D]\b", resp)
            if m:
                idx = ord(m.group()) - ord("A")
                if 0 <= idx < len(q.options) and q.options[idx] == q.correct_answer:
                    correct += 1
        acc = correct / len(questions) if questions else 0.0
        return acc, detailed

    # Execute a set of questions in one stage in parallel
    def _assess_stage_parallel(
        self, prefix: str, questions: List[Question], use_video_api: Optional[Callable[[str], str]] = None
    ) -> Tuple[float, List[str]]:
        api = use_video_api if use_video_api else self.mllm_api

        def build_prompt(i: int, q: Question) -> str:
            return f"{prefix}\n\n{self._format_mcq_prompt_block(i, q)}Please answer with a single letter (A|B|C|D) then a brief explanation."

        responses: List[Optional[str]] = [None] * len(questions)
        with ThreadPoolExecutor(max_workers=self.per_question_workers) as pool:
            futures = {}
            for i, q in enumerate(questions, 1):
                prompt = build_prompt(i, q)
                fut = pool.submit(api, prompt)
                futures[fut] = i - 1  # Subscript
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    responses[idx] = fut.result()
                except Exception as e:
                    responses[idx] = ""  # Failed responses are marked empty, counted as wrong
        # Fill None with empty strings
        responses = [r if r is not None else "" for r in responses]
        return self._grade_batch(questions, responses)

    def assess_baseline(self, concept: str, questions: List[Question]) -> Tuple[float, List[str]]:
        prefix = "You are taking a multiple-choice test. Output: letter on first line, then brief explanation."
        return self._assess_stage_parallel(prefix, questions)

    def assess_with_unlearning(self, concept: str, questions: List[Question]) -> Tuple[float, List[str]]:
        prefix = get_unlearning_prompt(concept)
        return self._assess_stage_parallel(prefix, questions)

    def assess_with_unlearning_and_video(self, concept: str, questions: List[Question], video_api_fn) -> Tuple[float, List[str]]:
        prefix = get_unlearning_and_video_learning_prompt(concept)
        return self._assess_stage_parallel(prefix, questions, use_video_api=video_api_fn)

    def evaluate_educational_video(
        self, concept: str, questions: List[Question], video_api_fn: Callable[[str], str]
    ) -> EvaluationResult:
        print(f"Start evaluation: {concept}")

        # Step 1：Baseline
        print("Step 1: Baseline (no unlearning, no video)")
        pre_score, pre_resps = self.assess_baseline(concept, questions)
        print(f"Baseline score: {pre_score:.3f}")

        # Step 2：Unlearning-only
        print("Step 2: Unlearning-only")
        post_unlearn_score, post_unlearn_resps = self.assess_with_unlearning(concept, questions)
        print(f"Unlearning-only score: {post_unlearn_score:.3f}")
        unlearn_success = post_unlearn_score <= pre_score  # 简单启发式

        # Step 3：Unlearning + Video
        print("Step 3: Unlearning + Video")
        post_video_score, post_video_resps = self.assess_with_unlearning_and_video(concept, questions, video_api_fn)
        print(f"Unlearning + Video score: {post_video_score:.3f}")

        # Overall Score
        gain = post_video_score - post_unlearn_score
        result = EvaluationResult(
            concept=concept,
            pre_unlearning_score=pre_score,
            post_unlearning_score=post_unlearn_score,
            post_video_score=post_video_score,
            unlearning_success=unlearn_success,
            learning_gain=gain,
            detailed_responses={"baseline": pre_resps, "post_unlearning": post_unlearn_resps, "post_video": post_video_resps},
        )
        print(f"Done: gain={gain:.3f}")
        return result


def format_evaluation_report(results: List[EvaluationResult]) -> str:
    report = """
========================================
SKU EDUCATIONAL VIDEO EVALUATION REPORT
========================================

"""

    if not results:
        return report + "No results.\n"

    total_concepts = len(results)
    successful_unlearning = sum(1 for r in results if r.unlearning_success)
    gains = [r.learning_gain for r in results]
    pre_scores = [r.pre_unlearning_score for r in results]
    post_unlearn_scores = [r.post_unlearning_score for r in results]
    post_video_scores = [r.post_video_score for r in results]

    def _safe_mean(xs):
        return float(np.mean(xs)) if len(xs) > 0 else float("nan")

    report += "DETAILED RESULTS BY CONCEPT:\n"

    for result in results:
        effectiveness_rating = "High" if result.learning_gain > 0.3 else "Medium" if result.learning_gain > 0.1 else "Low"
        report += f"""
        CONCEPT: {result.concept}
        ├── Unlearning Success: {'✓' if result.unlearning_success else '✗'}
        ├── Pre-unlearning Score: {result.pre_unlearning_score:.3f}
        ├── Post-unlearning Score: {result.post_unlearning_score:.3f}
        ├── Post-video Score: {result.post_video_score:.3f}
        ├── Learning Gain: {result.learning_gain:.3f}
        └── Video Effectiveness: {effectiveness_rating}

        """

    # statistical significance
    successful_results = [r for r in results if r.unlearning_success]
    if len(successful_results) > 1:
        successful_gains = [r.learning_gain for r in successful_results]
        t_stat, p_value = stats.ttest_1samp(successful_gains, 0)
        mu = float(np.mean(successful_gains))
        sd = float(np.std(successful_gains, ddof=1)) if len(successful_gains) > 1 else 0.0
        n = len(successful_gains)
        ci_low = mu - 1.96 * (sd / np.sqrt(n)) if n > 1 and sd > 0 else mu
        ci_high = mu + 1.96 * (sd / np.sqrt(n)) if n > 1 and sd > 0 else mu
        d = (mu / sd) if sd > 0 else float("inf")

        report += f"""
        STATISTICAL ANALYSIS (on successfully unlearned concepts):
        - Learning Gain Distribution: μ={mu:.3f}, σ={sd:.3f}, n={n}
        - Significance Test (H0: no learning): t={t_stat:.3f}, p={p_value:.3f}
        - Effect Size (Cohen's d): {d:.3f}
        - 95% Confidence Interval: [{ci_low:.3f}, {ci_high:.3f}]

        """

    report += "=" * 50 + "\n\n"
    report += f"""
SUMMARY STATISTICS:
- Total Concepts Evaluated: {total_concepts}
- Successful Unlearning Rate: {successful_unlearning}/{total_concepts} ({(successful_unlearning/total_concepts*100):.1f}%)
- Average Pre-unlearning Score: {_safe_mean(pre_scores):.3f}
- Average Post-unlearning Score: {_safe_mean(post_unlearn_scores):.3f}
- Average Post-video Score: {_safe_mean(post_video_scores):.3f}
- Average Learning Gain: {_safe_mean(gains)*100:.1f}

"""

    return report


def run_one_concept(concept: str, questions: List[Question], video_path: str, per_question_workers: int) -> EvaluationResult:
    text_api = make_mllm_api(video_path=None)
    video_api = make_mllm_api(video_path=video_path)
    sku = SelectiveKnowledgeUnlearning(mllm_api_function=text_api, per_question_workers=per_question_workers)
    return sku.evaluate_educational_video(concept=concept, questions=questions, video_api_fn=video_api)


def main():
    parser = argparse.ArgumentParser(description="Run SKU evaluation over a question JSON and generated videos (parallel).")
    parser.add_argument("--concept_workers", type=int, default=2, help="Parallel workers across concepts.")
    parser.add_argument("--per_question_workers", type=int, default=5, help="Parallel workers per concept per stage.")
    parser.add_argument(
        "--questions_json",
        type=str,
        default="/mlx_devbox/users/chenanno/playground/Code4Video/pipeline/json_files/questions_by_topic_10.json",
        help="Path to the questions JSON file.",
    )
    parser.add_argument(
        "--concepts",
        type=str,
        nargs="*",
        default=None,
        help="Optional subset of concepts to evaluate. If not set, evaluate all in JSON.",
    )
    # TODO: CASES 下的路径
    parser.add_argument(
        "--base_dir",
        type=str,
        default="/mlx_devbox/users/chenanno/playground/Code4Video/pipeline/CASES/Sep_Gemini",
        help="Base directory where per-knowledge-point video folders are located",
    )
    # TODO: Test the number of knowledge points. If None, test all of them
    parser.add_argument("--max_concepts", default=None)
    args = parser.parse_args()
    # 1) Load the question set
    concept_questions = load_questions_from_json(args.questions_json)
    all_concepts = list(concept_questions.keys())
    chosen_concepts = [c for c in all_concepts if (not args.concepts or c in args.concepts)]
    if args.max_concepts is not None:
        chosen_concepts = chosen_concepts[: args.max_concepts]
    if not chosen_concepts:
        print("[ERROR] No concepts to evaluate. Check --concepts or the JSON content.")
        return
    # 2) Generate a list of video paths
    video_items = eva_video_list(chosen_concepts, args.base_dir)
    concept2video = {item["knowledge_point"]: item["path"] for item in video_items}
    # 3) Parallel execution
    results: List[EvaluationResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concept_workers)) as pool:
        futures = {}
        for concept in chosen_concepts:
            qs = concept_questions.get(concept, [])
            if not qs:
                print(f"[WARN] No questions for concept '{concept}', skip.")
                continue
            vpath = concept2video.get(concept)
            if not vpath:
                print(f"[WARN] No video path for concept '{concept}', skip.")
                continue
            if not Path(vpath).exists():
                print(f"[WARN] Video file not found: {vpath} (concept '{concept}'). API may fail.")
            fut = pool.submit(run_one_concept, concept, qs, vpath, args.per_question_workers)
            futures[fut] = concept
        for fut in as_completed(futures):
            concept = futures[fut]
            try:
                res = fut.result()
                results.append(res)
            except Exception as e:
                print(f"[ERROR] Concept '{concept}' failed with error: {e}")
    # 4) Summarize the report
    report = format_evaluation_report(results)
    print(report)


if __name__ == "__main__":
    main()
