import re
from pathlib import Path
import json
from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)


def get_completion_only(result):
    if isinstance(result, tuple) and len(result) >= 1:
        return result[0]


class ManimCodeErrorAnalyzer:
    """Intelligently analyze Manim code errors and accurately locate the problems"""

    def __init__(self):
        self.common_manim_errors = {
            "NameError": self._analyze_name_error,
            "AttributeError": self._analyze_attribute_error,
            "TypeError": self._analyze_type_error,
            "ValueError": self._analyze_value_error,
            "ImportError": self._analyze_import_error,
            "SyntaxError": self._analyze_syntax_error,
            "IndentationError": self._analyze_indentation_error,
        }

    def analyze_error(self, code: str, error_msg: str) -> Dict:
        """Analyze errors and return precise error messages"""
        error_info = {
            "error_type": None,
            "line_number": None,
            "column": None,
            "problematic_code": None,
            "context_lines": [],
            "suggested_fix": None,
            "fix_scope": "single_line",
            "relevant_code_block": None,
        }

        # Parse the error message
        error_info.update(self._parse_error_message(error_msg))

        # Conduct specific analysis based on the type of error
        if error_info["error_type"] in self.common_manim_errors:
            analyzer = self.common_manim_errors[error_info["error_type"]]
            error_info.update(analyzer(code, error_msg, error_info))

        # Extract the relevant code blocks
        error_info["relevant_code_block"] = self._extract_relevant_code_block(code, error_info)
        return error_info

    def _parse_error_message(self, error_msg: str) -> Dict:
        """Parse the error message and extract basic information"""
        result = {}

        # Extract the error type
        error_type_match = re.search(r"(\w+Error|\w+Exception)", error_msg)
        if error_type_match:
            result["error_type"] = error_type_match.group(1)

        # Extract the line number
        line_match = re.search(r"line (\d+)", error_msg)
        if line_match:
            result["line_number"] = int(line_match.group(1))

        # Extract the column number
        column_match = re.search(r"column (\d+)", error_msg)
        if column_match:
            result["column"] = int(column_match.group(1))

        # Extract the problematic code
        code_match = re.search(r'File ".*?", line \d+.*?\n\s*(.*)', error_msg)
        if code_match:
            result["problematic_code"] = code_match.group(1).strip()

        return result

    def _analyze_name_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze NameError"""
        # Extract the undefined variable name
        name_match = re.search(r"name '(\w+)' is not defined", error_msg)
        if name_match:
            undefined_name = name_match.group(1)

            # Check if it's a common Manim object
            manim_suggestions = self._get_manim_suggestions(undefined_name)
            if manim_suggestions:
                return {
                    "fix_scope": "single_line",
                    "suggested_fix": f"May be need to import or create: {', '.join(manim_suggestions)}",
                    "undefined_variable": undefined_name,
                }

        return {"fix_scope": "single_line"}

    def _analyze_attribute_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze AttributeError"""
        # Extract the object and attribute
        attr_match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error_msg)
        if attr_match:
            obj_type, attr_name = attr_match.groups()

            # Check if it's a common Manim object attribute error
            suggestion = self._get_attribute_suggestion(obj_type, attr_name)
            if suggestion:
                return {
                    "fix_scope": "single_line",
                    "suggested_fix": suggestion,
                    "object_type": obj_type,
                    "attribute_name": attr_name,
                }

        return {"fix_scope": "single_line"}

    def _analyze_type_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze TypeError"""
        # Check if it's a parameter error
        if "takes" in error_msg and "positional arguments" in error_msg:
            return {"fix_scope": "single_line", "suggested_fix": "Check the number of parameters in the function call"}

        # Check if it's a type mismatch error
        if "unsupported operand type" in error_msg:
            return {"fix_scope": "single_line", "suggested_fix": "Check whether the operand types match"}

        return {"fix_scope": "function"}

    def _analyze_value_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze ValueError"""
        return {"fix_scope": "single_line"}

    def _analyze_import_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze ImportError"""
        return {"fix_scope": "single_line", "suggested_fix": "Check whether the import statement is correct"}

    def _analyze_syntax_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze SyntaxError"""
        return {"fix_scope": "single_line", "suggested_fix": "Check for grammar errors: parenthesis matching, indentation, etc"}

    def _analyze_indentation_error(self, code: str, error_msg: str, error_info: Dict) -> Dict:
        """Analyze IndentationError"""
        return {"fix_scope": "single_line", "suggested_fix": "Check if the indentation is correct"}

    def _extract_relevant_code_block(self, code: str, error_info: Dict) -> str:
        """Extract the relevant code block based on the error information"""
        lines = code.split("\n")

        if error_info["fix_scope"] == "single_line" and error_info["line_number"]:
            # Single line error: return the error line and surrounding lines
            line_num = error_info["line_number"] - 1  # Convert to 0-indexed
            start = max(0, line_num - 5)
            end = min(len(lines), line_num + 5)
            return "\n".join(lines[start:end])

        elif error_info["fix_scope"] == "function":
            # Function level error: find the function containing the error
            return self._extract_function_containing_line(code, error_info["line_number"])

        elif error_info["fix_scope"] == "section":
            # Section level error: find the animation section containing the error
            return self._extract_animation_section(code, error_info["line_number"])

        return code  # If the scope cannot be determined, return the entire code

    def _extract_function_containing_line(self, code: str, line_number: int) -> str:
        """Extract the function containing the specified line number"""
        lines = code.split("\n")

        # From the error line, go up to find the function definition
        for i in range(line_number - 1, -1, -1):
            if lines[i].strip().startswith("def "):
                # Found the function start, now find the function end
                indent_level = len(lines[i]) - len(lines[i].lstrip())
                func_start = i
                func_end = len(lines)

                for j in range(i + 1, len(lines)):
                    if lines[j].strip() and (len(lines[j]) - len(lines[j].lstrip())) <= indent_level:
                        func_end = j
                        break

                return "\n".join(lines[func_start:func_end])

        # If no function is found, return the surrounding lines
        start = max(0, line_number - 5)
        end = min(len(lines), line_number + 5)
        return "\n".join(lines[start:end])

    def _extract_animation_section(self, code: str, line_number: int) -> str:
        """Extract the animation section containing the specified line number"""
        lines = code.split("\n")

        # Find the animation section that contains the error line
        section_start = None
        section_end = None

        for i, line in enumerate(lines):
            if re.match(r"\s*# === Animation for Lecture Line \d+ ===", line):
                if section_start is None:
                    section_start = i
                elif i > line_number:
                    section_end = i
                    break

        if section_start is not None:
            if section_end is None:
                section_end = len(lines)
            return "\n".join(lines[section_start:section_end])

        return self._extract_function_containing_line(code, line_number)

    def _get_manim_suggestions(self, undefined_name: str) -> List[str]:
        """Get suggestions for Manim-related undefined names"""
        manim_objects = {
            "Text": "from manim import Text",
            "Circle": "from manim import Circle",
            "Square": "from manim import Square",
            "VGroup": "from manim import VGroup",
            "Create": "from manim import Create",
            "Write": "from manim import Write",
            "FadeIn": "from manim import FadeIn",
            "FadeOut": "from manim import FadeOut",
            "Transform": "from manim import Transform",
        }

        suggestions = []
        for obj_name, import_stmt in manim_objects.items():
            if undefined_name.lower() in obj_name.lower() or obj_name.lower() in undefined_name.lower():
                suggestions.append(import_stmt)

        return suggestions

    def _get_attribute_suggestion(self, obj_type: str, attr_name: str) -> str:
        """Get suggestions for attributes of a Manim object"""
        common_fixes = {
            "Text": {"color": "set_color()", "font": "font_size parameter in constructor"},
            "Mobject": {"move_to": "move_to() method exists", "shift": "shift() method exists"},
        }

        if obj_type in common_fixes and attr_name in common_fixes[obj_type]:
            return f"Try to use {common_fixes[obj_type][attr_name]}"

        return f"Check whether the {obj_type} object has the {attr_name} attribute"


class ScopeRefineFixer:

    def __init__(self, gpt_request_func, MAX_CODE_TOKEN_LENGTH):
        self.analyzer = ManimCodeErrorAnalyzer()
        self.request_gpt = gpt_request_func
        self.MAX_CODE_TOKEN_LENGTH = MAX_CODE_TOKEN_LENGTH

        self.common_fixes = self._load_common_fixes()
        self.error_patterns = self._load_error_patterns()

    def _load_common_fixes(self) -> Dict[str, str]:
        """Load common error fix patterns"""
        return {
            "AttributeError": "Object property error. Check the method name and property name",
            "NameError": "The variable is undefined. Check the variable declaration and scope",
            "TypeError": "Type error. Check the parameter type and quantity",
            "ImportError": "Import error. Check the module name and version compatibility",
            "ValueError": "The value is incorrect. Check the validity of the parameter value",
            "IndexError": "Index error. Check the list/array boundary",
            "KeyError": "Key error. Check the existence of the dictionary key",
        }

    def _load_error_patterns(self) -> Dict[str, Dict]:
        """Load error patterns and corresponding fix strategies"""
        return {
            "manim_import_error": {
                "pattern": r"No module named.*manim",
                "fix": "Make sure to import correctly: from manim import *",
            },
            "scene_method_error": {
                "pattern": r"'.*Scene'.*has no attribute",
                "fix": "Check the method names of the Scene class to ensure that the correct Manim API is used",
            },
            "mobject_error": {
                "pattern": r".*Mobject.*has no attribute",
                "fix": "Check the methods and properties of Mobject to ensure version compatibility",
            },
            "animation_error": {"pattern": r".*Animation.*", "fix": "Check the parameters and usage of the animation class"},
            "syntax_error": {"pattern": r"SyntaxError|IndentationError", "fix": "Fix grammar errors and indentation issues"},
        }

    def classify_error(self, error_msg: str) -> Tuple[str, str, List[str]]:
        """Classify errors and provide fix suggestions"""
        error_type = "Unknown"
        error_category = "general"
        suggestions = []

        # Extract error type
        for err_type in self.common_fixes.keys():
            if err_type in error_msg:
                error_type = err_type
                suggestions.append(self.common_fixes[err_type])
                break

        # Match specific error patterns
        for category, pattern_info in self.error_patterns.items():
            if re.search(pattern_info["pattern"], error_msg, re.IGNORECASE):
                error_category = category
                suggestions.append(pattern_info["fix"])
                break

        return error_type, error_category, suggestions

    def extract_error_context(self, error_msg: str) -> Dict[str, Any]:
        """Extract error context information"""
        context = {"line_number": None, "error_line": None, "traceback": error_msg, "specific_error": None}

        # Extract line number
        line_match = re.search(r"line (\d+)", error_msg)
        if line_match:
            context["line_number"] = int(line_match.group(1))

        # Extract specific error information
        lines = error_msg.split("\n")
        for line in reversed(lines):
            if line.strip() and not line.startswith("  "):
                context["specific_error"] = line.strip()
                break

        return context

    def validate_code_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """Validate code syntax correctness"""
        try:
            compile(code, "<string>", "exec")
            return True, None
        except SyntaxError as e:
            return False, f"Syntax Error: {e}"
        except Exception as e:
            return False, f"Compilation Error: {e}"

    def dry_run_test(self, code: str, section_id: str, output_dir: Path) -> Tuple[bool, Optional[str]]:
        """Execute dry run test (do not render video)"""
        test_file = output_dir / f"test_{section_id}.py"

        # Create test version of code (add quick exit)
        test_code = code.replace(
            "def construct(self):",
            "def construct(self):\n        # Dry run test - quick exit\n        self.wait(0.1)\n        return\n        # Original code below:",
        )

        try:
            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_code)

            scene_name = f"{section_id.title().replace('_', '')}Scene"
            cmd = ["python", "-c", f"from test_{section_id} import {scene_name}; scene = {scene_name}(); print('Syntax OK')"]

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=output_dir, timeout=10)

            test_file.unlink()  # Clean up test file

            if result.returncode == 0:
                return True, None
            else:
                return False, result.stderr

        except Exception as e:
            if test_file.exists():
                test_file.unlink()
            return False, str(e)

    def _clean_code_format(self, code: str) -> Optional[str]:
        """Clean and format code"""
        if not code:
            return None

        # Remove markdown code block markers
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].strip()

        # Remove extra empty lines
        lines = code.split("\n")
        cleaned_lines = []
        prev_empty = False

        for line in lines:
            if line.strip():
                cleaned_lines.append(line)
                prev_empty = False
            elif not prev_empty:
                cleaned_lines.append(line)
                prev_empty = True

        return "\n".join(cleaned_lines)

    def generate_fix_prompt(self, section_id: str, current_code: str, error_msg: str, attempt: int) -> str:
        """Generate high-quality fix prompt"""
        error_type, error_category, suggestions = self.classify_error(error_msg)
        error_context = self.extract_error_context(error_msg)

        # Adjust fix strategy based on attempt number
        if attempt == 1:
            strategy = "focused_fix"
        elif attempt == 2:
            strategy = "comprehensive_review"
        else:
            strategy = "complete_rewrite"

        base_prompt = f"""
        You are an expert Manim Community Edition v0.19.0 developer. Fix the following code error with high precision.

        **Error Analysis:**
        - Error Type: {error_type}
        - Error Category: {error_category}
        - Attempt: {attempt}/3
        - Strategy: {strategy}

        **Error Message:**
        ```
        {error_msg}
        ```

        **Current Code:**
        ```python
        {current_code}
        ```

        **Error Context:**
        {json.dumps(error_context, indent=2)}

        **Suggestions:**
        {chr(10).join(f"- {s}" for s in suggestions)}
        """

        if strategy == "focused_fix":
            specific_prompt = """
            **FOCUSED FIX (Attempt 1):**
            - Only fix the specific error mentioned
            - Maintain the original code structure
            - Make minimal necessary changes
            - Ensure all imports are correct for Manim CE v0.19.0
            - Verify method names and parameters match the API
            """

        elif strategy == "comprehensive_review":
            specific_prompt = """
            **COMPREHENSIVE REVIEW (Attempt 2):**
            - Review the entire code for potential issues
            - Check all Manim API usage for v0.19.0 compatibility
            - Verify variable declarations and scope
            - Ensure proper Scene inheritance and methods
            - Fix any animation timing or sequencing issues
            - Add error handling where appropriate
            """

        else:  # complete_rewrite
            specific_prompt = """
            **COMPLETE REWRITE (Attempt 3):**
            - Rewrite the scene with a simpler, more robust approach
            - Use only verified Manim CE v0.19.0 features
            - Implement basic animations that are guaranteed to work
            - Focus on functionality over complexity
            - Follow best practices for Scene construction
            """

        return (
            base_prompt
            + specific_prompt
            + """

            **Requirements:**
            1. Output ONLY the complete, fixed Python code
            2. No explanations or comments outside the code
            3. Ensure the code is syntactically correct
            4. Test all variable names and method calls
            5. Use proper Manim CE v0.19.0 syntax

            **Code:**"""
        )

    def fix_code_smart(self, section_id: str, code: str, error_msg: str, output_dir: Path) -> Optional[str]:
        """Smart fix code, prioritize local fix, fallback to complete rewrite if failed"""

        # Analyze error
        error_info = self.analyzer.analyze_error(code, error_msg)
        # Decide on fix scope based on error analysis
        if error_info["fix_scope"] in ["single_line", "function", "section"]:

            relevant_code = error_info.get("relevant_code_block")
            if relevant_code:
                fixed_block = self._fix_code_block(section_id, relevant_code, error_msg, error_info)
                if fixed_block:
                    merged_code = self._merge_fixed_block(code, relevant_code, fixed_block, error_info)
                    if merged_code:
                        is_valid, syntax_error = self.validate_code_syntax(merged_code)
                        if is_valid:
                            is_dry_run_ok, dry_run_error = self.dry_run_test(merged_code, section_id, output_dir)
                            if is_dry_run_ok:
                                return merged_code
                            else:
                                print(f"⚠️ The dry run failed after local repair: {dry_run_error}")
                        else:
                            print(f"⚠️ The syntax error after local repair: {syntax_error}")
                    else:
                        print("⚠️ The code block merge failed after local repair")
                else:
                    print("⚠️ The local repair failed after local repair")
            else:
                print("⚠️ The relevant code block cannot be extracted after local repair")
        else:
            print("🔄 The error scope is large, directly use complete repair")

        print("⚠️ The smart repair failed, fallback to complete repair")
        return self.fix_code_with_multi_stage_validation(section_id, code, error_msg, output_dir)

    def fix_code_with_multi_stage_validation(
        self, section_id: str, current_code: str, error_msg: str, output_dir: Path, max_attempts: int = 3
    ) -> Optional[str]:
        """Multi-stage validation code repair"""
        logger.info(f"Start fixing the code errors for {section_id}")

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Start fixing the code errors for {section_id} attempt {attempt}/{max_attempts}")

            try:
                fix_prompt = self.generate_fix_prompt(section_id, current_code, error_msg, attempt)
                response = self.request_gpt(fix_prompt, max_tokens=self.MAX_CODE_TOKEN_LENGTH)
                response = get_completion_only(response)

                if hasattr(response, "choices") and response.choices:
                    fixed_code = response.choices[0].message.content
                elif isinstance(response, str):
                    fixed_code = response
                else:
                    fixed_code = str(response)

                fixed_code = self._clean_code_format(fixed_code)

                if not fixed_code:
                    logger.warning(f"Attempt {attempt}: Failed to extract valid code")
                    continue

                # Stage 1: Syntax validation
                is_valid_syntax, syntax_error = self.validate_code_syntax(fixed_code)
                if not is_valid_syntax:
                    logger.warning(f"Attempt {attempt}: Syntax error - {syntax_error}")
                    error_msg = syntax_error  # Update the error message for the next fix
                    current_code = fixed_code  # Update the current code
                    continue

                logger.info(f"Attempt {attempt}: Syntax validation passed")

                # Stage 2: Dry run test
                is_dry_run_ok, dry_run_error = self.dry_run_test(fixed_code, section_id, output_dir)
                if not is_dry_run_ok:
                    logger.warning(f"Attempt {attempt}: Dry run failed - {dry_run_error}")
                    error_msg = dry_run_error
                    current_code = fixed_code
                    continue

                logger.info(f"Attempt {attempt}: Dry run test passed")

                return fixed_code

            except Exception as e:
                logger.error(f"Attempt {attempt} fix process encountered an exception: {e}")
                continue

        logger.error(f"{section_id} fix failed - Reached maximum attempts")
        return None

    def _fix_code_block(self, section_id: str, code_block: str, error_msg: str, error_info: Dict) -> Optional[str]:
        """Fix the code block"""
        # Enhanced error analysis information
        error_type, error_category, suggestions = self.classify_error(error_msg)
        error_context = self.extract_error_context(error_msg)

        prompt = f"""
        You are an expert Manim Community Edition v0.19.0 developer. Fix the error in the following code block.

        **Error Analysis:**
        - Error Type: {error_type}
        - Error Category: {error_category}
        - Fix Scope: {error_info.get('fix_scope', 'unknown')}
        - Suggested Fix: {error_info.get('suggested_fix', 'None')}

        **Error Message:**
        ```
        {error_msg}
        ```

        **Error Context:**
        {json.dumps(error_context, indent=2)}

        **Suggestions:**
        {chr(10).join(f"- {s}" for s in suggestions)}

        **Code Block to Fix:**
        ```python
        {code_block}
        ```

        **Requirements:**
        1. Only fix the specific error mentioned
        2. Maintain the original code structure and logic
        3. Make minimal necessary changes
        4. Ensure compatibility with Manim CE v0.19.0
        5. Output ONLY the fixed Python code block

        **Fixed Code:**
        """

        try:
            response = self.request_gpt(prompt, max_tokens=self.MAX_CODE_TOKEN_LENGTH)
            response = get_completion_only(response)
            if hasattr(response, "choices") and response.choices:
                fixed_code = response.choices[0].message.content
            elif isinstance(response, str):
                fixed_code = response
            else:
                fixed_code = str(response)
            return self._clean_code_format(fixed_code)

        except Exception as e:
            print(f"Fix code block failed: {e}")
            return None

    def _merge_fixed_block(self, original_code: str, original_block: str, fixed_block: str, error_info: Dict) -> Optional[str]:
        """Merge the fixed code block back into the original code"""
        try:
            # Simple string replacement
            if original_block in original_code:
                merged_code = original_code.replace(original_block, fixed_block)
                return merged_code

            # If direct replacement fails, try more intelligent merging
            # Based on error context information for more precise replacement
            if error_info.get("line_number"):
                lines = original_code.split("\n")
                original_lines = original_block.split("\n")
                fixed_lines = fixed_block.split("\n")

                # Try line-based replacement based on error context
                line_number = error_info["line_number"]
                if 1 <= line_number <= len(lines):
                    # Find the matching line range
                    start_idx = None
                    for i, line in enumerate(lines):
                        if line.strip() == original_lines[0].strip():
                            start_idx = i
                            break

                    if start_idx is not None:
                        end_idx = start_idx + len(original_lines)
                        if end_idx <= len(lines):
                            # Replace the matching lines with fixed lines
                            new_lines = lines[:start_idx] + fixed_lines + lines[end_idx:]
                            return "\n".join(new_lines)

            # If all intelligent merging fails, return None to let the system fallback to full repair
            print("⚠️ Code block merging failed, will fallback to full repair")
            return None

        except Exception as e:
            print(f"Error merging code block: {e}")
            return None


@dataclass
class GridPosition:
    """Grid position information"""

    object_name: str
    method: str  # 'place_at_grid' or 'place_in_area'
    position: str  # 'B2' or 'A1-C3'
    scale_factor: Optional[float] = None
    line_number: int = 0
    original_code: str = ""


class GridPositionExtractor:
    """Extract grid position information from Manim code"""

    def __init__(self):
        # Match place_at_grid and place_in_area methods
        self.grid_patterns = [
            r'self\.place_at_grid\(\s*([^,]+),\s*[\'"]([A-F][1-6])[\'"](?:,\s*scale_factor=([0-9.]+))?\s*\)',
            r'self\.place_in_area\(\s*([^,]+),\s*[\'"]([A-F][1-6])[\'"],\s*[\'"]([A-F][1-6])[\'"](?:,\s*scale_factor=([0-9.]+))?\s*\)',
        ]

    def extract_grid_positions(self, code: str) -> List[GridPosition]:
        """Extract all grid position information from the code"""
        positions = []
        lines = code.split("\n")

        for line_num, line in enumerate(lines, 1):
            # Check place_at_grid
            match = re.search(self.grid_patterns[0], line)
            if match:
                obj_name = match.group(1).strip()
                grid_pos = match.group(2)
                scale = float(match.group(3)) if match.group(3) else None

                positions.append(
                    GridPosition(
                        object_name=obj_name,
                        method="place_at_grid",
                        position=grid_pos,
                        scale_factor=scale,
                        line_number=line_num,
                        original_code=line.strip(),
                    )
                )

            # Check place_in_area
            match = re.search(self.grid_patterns[1], line)
            if match:
                obj_name = match.group(1).strip()
                start_pos = match.group(2)
                end_pos = match.group(3)
                scale = float(match.group(4)) if match.group(4) else None

                positions.append(
                    GridPosition(
                        object_name=obj_name,
                        method="place_in_area",
                        position=f"{start_pos}-{end_pos}",
                        scale_factor=scale,
                        line_number=line_num,
                        original_code=line.strip(),
                    )
                )

        return positions

    def generate_position_table(self, positions: List[GridPosition]) -> str:
        """Generate a position table for MLLM analysis"""
        if not positions:
            return "No grid positions found in the code."

        table = "Current Grid Layout Positions:\n"
        table += "|Object|Method|Position|Scale|Line|\n"

        for pos in positions:
            scale_str = str(pos.scale_factor) if pos.scale_factor else "default"
            table += f"|{pos.object_name}|{pos.method}|{pos.position}|{scale_str}|{pos.line_number}|\n"

        return table


class GridCodeModifier:
    """Modify specific grid position code based on feedback"""

    def __init__(self, original_code: str):
        self.original_code = original_code
        self.lines = original_code.split("\n")

    def apply_grid_modifications(self, modifications: List[Dict[str, Any]]) -> str:
        modified_lines = self.lines.copy()
        for mod in modifications:
            try:
                line_idx = int(mod["line_number"]) - 1
            except Exception:
                continue
            if not (0 <= line_idx < len(modified_lines)):
                continue
            original_line = modified_lines[line_idx]
            # print(f"Replace line {line_idx + 1}: {original_line} -> {mod['new_code'].strip()}")
            indent = len(original_line) - len(original_line.lstrip())
            new_code = " " * indent + mod["new_code"].strip()
            modified_lines[line_idx] = new_code
        return "\n".join(modified_lines)

    def parse_feedback_and_modify(self, feedback_list: List[str]) -> str:
        """feedback_list: ['... Solution: Line 121: self.place_at_grid(... )', ...]"""
        if not isinstance(feedback_list, list):
            return self.original_code

        modifications: List[Dict[str, Any]] = []
        line_pat = re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)
        call_pat = re.compile(r"self\.(?:place_at_grid|place_in_area)\([^\n\r]*?\)")

        for item in feedback_list:
            if not isinstance(item, str):
                continue
            # Extract line number and new code from feedback
            m_sol = re.search(r"solution\s*:\s*(.*)$", item, flags=re.IGNORECASE)
            sol = m_sol.group(1).strip() if m_sol else item.strip()
            # Extract line number from feedback
            m_line = line_pat.search(sol)
            if not m_line:
                continue
            line_number = int(m_line.group(1))
            # Extract new code from feedback
            m_call = call_pat.search(sol)
            if not m_call:
                continue
            new_code = m_call.group(0)
            modifications.append({"line_number": line_number, "new_code": new_code})
        return self.apply_grid_modifications(modifications)
