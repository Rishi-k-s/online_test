"""
ESP-IDF StdIO Evaluator for Yaksh
"""
import os
import shutil
import subprocess
import logging
import signal
from yaksh.base_evaluator import BaseEvaluator
from yaksh.grader import TimeoutException

# Setup logging for detailed diagnostics
logger = logging.getLogger(__name__)

class EspIdfStdIOEvaluator(BaseEvaluator):
    """
    Evaluator for ESP-IDF code using QEMU and arduino_to_esp/ino_to_running.sh
    """
    def __init__(self, metadata, test_case_data):
        self.files = []
        self.script_path = os.path.join(os.path.dirname(__file__), 'arduino_to_esp/ino_to_running.sh')
        self.output_file = os.path.join(os.path.dirname(__file__), 'arduino_to_esp/filtered_output.txt')
        self.raw_output_file = os.path.join(os.path.dirname(__file__), 'arduino_to_esp/output.txt')
        self.build_log_file = os.path.join(os.path.dirname(__file__), 'arduino_to_esp/build.log')
        self.timeout = 20  # seconds, can be set from settings if needed

        # Set metadata values
        self.user_answer = metadata.get('user_answer')
        self.file_paths = metadata.get('file_paths')
        self.partial_grading = metadata.get('partial_grading')

        # Set test case data values
        self.expected_input = test_case_data.get('expected_input')
        self.expected_output = test_case_data.get('expected_output')
        self.weight = test_case_data.get('weight')
        self.hidden = test_case_data.get('hidden')
        
        # For diagnostics
        self.diagnostic_info = ""
        self.compile_error = None  # Store compilation errors to show before output comparison

    def teardown(self):
        # No temp files to delete for now, but keep for interface compatibility
        pass

    def compile_code(self):
        # Write user code to temp .ino file in arduino_to_esp
        arduino_to_esp_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'arduino_to_esp'))
        ino_file = os.path.join(arduino_to_esp_dir, 'submission.ino')
        
        logger.info(f"[ESP-IDF Eval] Starting compilation for user code")
        logger.info(f"[ESP-IDF Eval] Arduino directory: {arduino_to_esp_dir}")
        logger.info(f"[ESP-IDF Eval] INO file path: {ino_file}")
        logger.info(f"[ESP-IDF Eval] Script path: {self.script_path}")
        
        # Write user answer to file
        try:
            with open(ino_file, 'w') as f:
                f.write(self.user_answer)
            logger.info(f"[ESP-IDF Eval] User code written to {ino_file}")
        except Exception as e:
            error_msg = f"Failed to write user code to file: {str(e)}"
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            return False, error_msg

        # Remove previous output files
        for output_file in [self.output_file, self.raw_output_file]:
            if os.path.exists(output_file):
                try:
                    os.remove(output_file)
                    logger.info(f"[ESP-IDF Eval] Removed previous output file: {output_file}")
                except Exception as e:
                    logger.warning(f"[ESP-IDF Eval] Failed to remove {output_file}: {str(e)}")

        # Disable the global signal alarm during QEMU execution
        # ESP-IDF build + QEMU execution can take 15+ seconds, which exceeds Yaksh's default 4s timeout
        # We use our own subprocess timeout instead
        logger.info(f"[ESP-IDF Eval] Disabling global signal alarm for long-running QEMU execution")
        signal.alarm(0)  # Cancel any pending alarm
        
        # Run the script from arduino_to_esp directory
        logger.info(f"[ESP-IDF Eval] Executing build script with timeout={self.timeout}s")
        try:
            proc = subprocess.run([
                'bash', self.script_path, ino_file
            ], cwd=arduino_to_esp_dir,
               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout)
               
            stdout_text = proc.stdout.decode('utf-8') if proc.stdout else ""
            stderr_text = proc.stderr.decode('utf-8') if proc.stderr else ""
            
            logger.info(f"[ESP-IDF Eval] Script execution completed with return code: {proc.returncode}")
            if stdout_text:
                logger.info(f"[ESP-IDF Eval] Script STDOUT:\n{stdout_text}")
            if stderr_text:
                logger.warning(f"[ESP-IDF Eval] Script STDERR:\n{stderr_text}")
                
        except subprocess.TimeoutExpired:
            error_msg = f'Timeout: Compilation/QEMU execution exceeded {self.timeout}s time limit. QEMU may need more time to boot and execute. Consider increasing timeout.'
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            self.diagnostic_info = error_msg
            return False, error_msg
        
        except Exception as e:
            error_msg = f'Error running evaluator: {str(e)}'
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            self.diagnostic_info = error_msg
            return False, error_msg

        # Check for build/run errors
        if proc.returncode != 0:
            self.output_value = ''
            stderr = proc.stderr.decode('utf-8') if proc.stderr else ""
            stdout = proc.stdout.decode('utf-8') if proc.stdout else ""
            
            # Try to read and filter build.log for more details
            build_log_content = ""
            if os.path.exists(self.build_log_file):
                try:
                    with open(self.build_log_file, 'r') as f:
                        full_build_log = f.read()
                    logger.info(f"[ESP-IDF Eval] Full build log:\n{full_build_log}")
                    # Extract only the relevant error messages
                    build_log_content = self._extract_compiler_errors(full_build_log)
                except Exception as e:
                    logger.warning(f"[ESP-IDF Eval] Could not read build.log: {str(e)}")
            
            # If we have compilation errors, show only those (skip ESP-IDF setup output)
            if build_log_content:
                error_msg = f"Compilation Errors:\n{build_log_content}"
            else:
                error_msg = (f"Script failed with exit code {proc.returncode}.\n"
                            f"STDERR:\n{stderr}\n"
                            f"STDOUT:\n{stdout}")
                
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.diagnostic_info = error_msg
            self.compile_error = error_msg  # Store for check_code to display
            return False, error_msg

        # Read raw output first for diagnostics
        raw_output = ""
        if os.path.exists(self.raw_output_file):
            try:
                with open(self.raw_output_file, 'r') as f:
                    raw_output = f.read()
                logger.info(f"[ESP-IDF Eval] Raw QEMU output (first 500 chars):\n{raw_output[:500]}")
                logger.info(f"[ESP-IDF Eval] Raw output file size: {len(raw_output)} bytes")
            except Exception as e:
                logger.warning(f"[ESP-IDF Eval] Could not read raw output file: {str(e)}")
        else:
            logger.warning(f"[ESP-IDF Eval] Raw output file not found: {self.raw_output_file}")

        # Read filtered output (contains only actual program output, no bootloader messages)
        if not os.path.exists(self.output_file):
            error_msg = f'No filtered output generated by QEMU. Raw output file exists: {os.path.exists(self.raw_output_file)}, size: {len(raw_output) if raw_output else 0} bytes'
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            self.diagnostic_info = error_msg
            return False, error_msg
            
        try:
            with open(self.output_file, 'r') as f:
                self.output_value = f.read()
            logger.info(f"[ESP-IDF Eval] Filtered output (first 500 chars):\n{self.output_value[:500]}")
            logger.info(f"[ESP-IDF Eval] Filtered output file size: {len(self.output_value)} bytes")
        except Exception as e:
            error_msg = f'Error reading filtered output file: {str(e)}'
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            self.diagnostic_info = error_msg
            return False, error_msg
            
        logger.info(f"[ESP-IDF Eval] Compilation successful")
        return True, None

    def check_code(self):
        # Compare output using flexible sequence matching
        # Check if all expected lines appear in actual output in the same order
        # (but ignores extra lines like watchdog messages)
        
        def normalize(s):
            """Normalize by stripping whitespace from each line"""
            return '\n'.join(line.strip() for line in s.strip().splitlines() if line.strip())
        
        actual = normalize(self.output_value)
        expected = normalize(self.expected_output)
        
        # Split into lines for comparison
        expected_lines = expected.split('\n') if expected else []
        actual_lines = actual.split('\n') if actual else []
        
        # Flexible matching: check if all expected lines appear in actual output in sequence
        # Extra lines in actual output are ignored (e.g., watchdog messages)
        is_correct = True
        if expected_lines:
            expected_idx = 0
            for actual_line in actual_lines:
                if expected_idx < len(expected_lines) and expected_lines[expected_idx] == actual_line:
                    expected_idx += 1
            # All expected lines must be found
            is_correct = (expected_idx == len(expected_lines))
        else:
            # If no expected output, consider it correct if there's any output
            is_correct = bool(actual.strip())
        
        mark_fraction = self.weight
        
        logger.info(f"[ESP-IDF Eval] Output comparison (flexible sequence matching):")
        logger.info(f"[ESP-IDF Eval] Expected output:\n{expected}")
        logger.info(f"[ESP-IDF Eval] Actual output (first 500 chars):\n{actual[:500]}")
        logger.info(f"[ESP-IDF Eval] Expected lines: {len(expected_lines)}")
        logger.info(f"[ESP-IDF Eval] Actual lines: {len(actual_lines)}")
        logger.info(f"[ESP-IDF Eval] Match result: {is_correct}")
        
        # Build detailed error message
        error_msg = None
        
        # If there was a compilation error, show that first instead of output mismatch
        if self.compile_error:
            return False, self.compile_error, mark_fraction
        
        if not is_correct:
            # Show which expected lines are missing
            logger.warning(f"[ESP-IDF Eval] Output mismatch detected!")
            expected_idx = 0
            missing_lines = []
            
            for i, actual_line in enumerate(actual_lines):
                if expected_idx < len(expected_lines) and expected_lines[expected_idx] == actual_line:
                    logger.info(f"[ESP-IDF Eval] Line MATCHED: '{actual_line}'")
                    expected_idx += 1
            
            # Show missing expected lines
            if expected_idx < len(expected_lines):
                for j in range(expected_idx, len(expected_lines)):
                    missing_line = expected_lines[j]
                    missing_lines.append(f"Expected line NOT found: '{missing_line}'")
                    logger.warning(f"[ESP-IDF Eval] Expected line NOT found: '{missing_line}'")
            
            # Create detailed error message for user
            if missing_lines:
                error_msg = "Output mismatch:\n" + "\n".join(missing_lines)
            else:
                error_msg = "Expected output not found in actual output."
            
            if self.diagnostic_info:
                logger.warning(f"[ESP-IDF Eval] Diagnostic info: {self.diagnostic_info}")
        
        return is_correct, error_msg, mark_fraction
    def _extract_compiler_errors(self, build_log_content):
        """Extract only the relevant compiler error messages from build.log"""
        if not build_log_content:
            return ""
        
        lines = build_log_content.split('\n')
        error_lines = []
        
        # Collect all lines that are part of compiler errors
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for error/warning messages from the compiler
            if 'error:' in line or 'In function' in line:
                # For "In function" lines, simplify the path
                if 'In function' in line:
                    # Extract just the function part, remove the file path
                    parts = line.split(': In function ')
                    if len(parts) > 1:
                        error_lines.append(f"In function {parts[1]}")
                    else:
                        error_lines.append(line)
                # For error lines, simplify to show just line:col and error message
                elif 'error:' in line:
                    # Extract line number and error from: /path/to/file:13:22: error: message
                    if ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 4:
                            line_num = parts[1]
                            col_num = parts[2]
                            error_msg = ':'.join(parts[3:]).strip()
                            error_lines.append(f"Line {line_num}:{col_num}: {error_msg}")
                        else:
                            error_lines.append(line)
                    else:
                        error_lines.append(line)
                
                # For error lines, also include the context (source code and pointer lines)
                if 'error:' in line:
                    # Include the next few lines that show source code and error pointer
                    j = i + 1
                    while j < len(lines) and j < i + 10:
                        context_line = lines[j]
                        error_lines.append(context_line)
                        # Stop if we hit another compiler message or empty line followed by new error
                        if context_line.strip() == '' or context_line.startswith('/'):
                            break
                        # Also stop after showing the error pointer line (has spaces and ^ character)
                        if '^' in context_line and '|' in context_line:
                            j += 1
                            # Include one more line for the suggested fix (the ; line)
                            if j < len(lines) and '|' in lines[j]:
                                error_lines.append(lines[j])
                            break
                        j += 1
                    i = j - 1
            i += 1
        
        # Filter out build system messages
        filtered = []
        for line in error_lines:
            if not any(x in line for x in ['ninja:', 'subcommand failed', 'ninja failed']):
                filtered.append(line)
        
        return '\n'.join(filtered).strip()