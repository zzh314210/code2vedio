import os
import subprocess
from typing import List
from manim import *
import multiprocessing
import re
import psutil
from pathlib import Path


def extract_json_from_markdown(text):
    # Match ```json ... ``` or ``` ... ```
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    return text


def extract_answer_from_response(response):
    try:
        content = response.candidates[0].content.parts[0].text
    except Exception:
        try:
            content = response.choices[0].message.content
        except Exception:
            content = str(response)
    content = extract_json_from_markdown(content)
    return content


def fix_png_path(code_str: str, assets_dir: Path) -> str:
    assets_dir = Path(assets_dir).resolve()

    def replacer(match):
        original_path = match.group(1)  # matched XXX.png
        path_obj = Path(original_path)
        # not an absolute path and is not under assets_dir
        if not path_obj.is_absolute():
            # concat to absolute path
            return f'"{assets_dir / path_obj.name}"'
        # absolute path but not under assets_dir
        try:
            if assets_dir not in path_obj.parents:
                return f'"{assets_dir / path_obj.name}"'
        except RuntimeError:
            return f'"{assets_dir / path_obj.name}"'
        return match.group(0)  # keep original

    pattern = r'["\']([^"\']+\.png)["\']'
    return re.sub(pattern, replacer, code_str)


def get_optimal_workers():
    """Calculate the optimal number of parallel processes adaptively based on # CPU cores and load"""
    try:
        cpu_count = multiprocessing.cpu_count()
    except NotImplementedError:
        cpu_count = 6  # default

    # Manim rendering is CPU-intensive; usually set workers to CPU cores or cores minus one
    # reserve 1 core for system/other processes
    optimal = max(1, cpu_count - 1)

    # If the machine is high-performance multicore (>16 cores),
    # it's appropriate to limit the number of workers to avoid memory overflow
    if optimal > 16:
        optimal = 16

    print(f"⚙️ Detected {cpu_count} cores, using {optimal} parallel processes")
    return optimal


def monitor_system_resources():
    """Monitor system resource usage"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()

        print(f"📊 Resource usage: CPU {cpu_percent:.1f}% | Memory {memory.percent:.1f}%")

        if cpu_percent > 95:
            print("⚠️ CPU usage is high")
        if memory.percent > 90:
            print("⚠️ Memory usage is high")

        return True
    except Exception:
        return False


def replace_base_class(code: str, new_class_def: str) -> str:
    lines = code.splitlines(keepends=True)
    class_start = None
    class_end = None

    # Find the start line of class TeachingScene(Scene):
    for i, line in enumerate(lines):
        if re.match(r"^\s*class\s+TeachingScene\s*\(Scene\)\s*:", line):
            class_start = i
            break

    if class_start is not None:
        # Find the end line of the class definition
        # The class ends when a line with the same or less indentation is found
        base_indent = len(lines[class_start]) - len(lines[class_start].lstrip())
        class_end = class_start + 1
        while class_end < len(lines):
            line = lines[class_end]
            # If an empty line or a line with less indentation is found,
            # it means the class definition has ended
            if line.strip() != "" and (len(line) - len(line.lstrip()) <= base_indent):
                break
            class_end += 1

        # Replace the original TeachingScene definition with the new one
        new_block = new_class_def.strip() + "\n\n"
        return "".join(lines[:class_start]) + new_block + "".join(lines[class_end:])
    else:
        # If TeachingScene does not exist, it should be inserted before the first class definition
        for i, line in enumerate(lines):
            if re.match(r"^\s*class\s+\w+", line):
                insert_pos = i
                break
        else:
            insert_pos = 0

        new_block = new_class_def.strip() + "\n\n"
        return "".join(lines[:insert_pos]) + new_block + "".join(lines[insert_pos:])


# Save the program to the.py file
def save_code_to_file(code: str, filename: str = "scene.py"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"Saved code to {filename}")


# Run the manim code to generate a video
def run_manim_script(filename: str, scene_name: str, output_dir: str = "videos") -> str:
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{scene_name}.mp4")

    cmd = [
        "manim",
        "-pql",  # play + low quality（can changed to -pqm or -pqh）
        str(filename),  # script path
        scene_name,  # class name
        "--output_file",
        f"{scene_name}.mp4",
        "--media_dir",
        str(output_dir),  # media output directory
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print("Manim error:", result.stderr.decode())
        raise RuntimeError(f"Failed to render scene {scene_name}.")

    print(f"Video saved to {output_path}")
    return output_path


# Use ffmpeg to concatenate multiple mp4 files
def stitch_videos(video_files: List[str], output_path: str = "final_output.mp4"):
    list_file = "video_list.txt"
    with open(list_file, "w") as f:
        for vf in video_files:
            f.write(f"file '{os.path.abspath(vf)}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file, "-c", "copy", output_path]
    print("Stitching videos:", cmd)
    subprocess.run(cmd, check=True)
    print(f"Final stitched video saved to {output_path}")


def topic_to_safe_name(knowledge_point):
    # Allowed: alphanumeric Spaces _ - { } [ ] . , + & ' =
    SAFE_PATTERN = r"[^A-Za-z0-9 _\-\{\}\[\]\+&=\u03C0]"
    safe_name = re.sub(SAFE_PATTERN, "", knowledge_point)
    # Replace consecutive spaces with a single underscore
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    return safe_name


def get_output_dir(idx, knowledge_point, base_dir, get_safe_name=False):
    safe_name = topic_to_safe_name(knowledge_point)
    # Prefix with idx-
    folder_name = f"{idx}-{safe_name}"
    if get_safe_name:
        return Path(base_dir) / folder_name, safe_name

    return Path(base_dir) / folder_name


def eva_video_list(knowledge_points, base_dir):

    video_list = []
    for idx, kp in enumerate(knowledge_points):
        folder, safe_name = get_output_dir(idx, kp, base_dir, get_safe_name=True)

        # mp4 filename must be safe, the same
        mp4_name = f"{safe_name}.mp4"
        mp4_path = folder / mp4_name
        video_list.append({"path": str(mp4_path), "knowledge_point": kp})
    return video_list


if __name__ == "__main__":
    print(get_optimal_workers())
