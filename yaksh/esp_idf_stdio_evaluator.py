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
            
            # Try to read build.log for more details
            build_log_content = ""
            if os.path.exists(self.build_log_file):
                try:
                    with open(self.build_log_file, 'r') as f:
                        build_log_content = f.read()
                    logger.info(f"[ESP-IDF Eval] Build log content:\n{build_log_content}")
                except Exception as e:
                    logger.warning(f"[ESP-IDF Eval] Could not read build.log: {str(e)}")
            
            error_msg = (f"Script failed with exit code {proc.returncode}.\n"
                        f"STDERR:\n{stderr}\n"
                        f"STDOUT:\n{stdout}")
            if build_log_content:
                error_msg += f"\n\nBuild Log:\n{build_log_content}"
                
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.diagnostic_info = error_msg
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

        # Use raw output directly (more liberal approach)
        # Instead of using filtered output, we use raw output and check if expected is contained within
        if not raw_output:
            error_msg = f'No output generated by QEMU. Raw output file exists: {os.path.exists(self.raw_output_file)}, size: {len(raw_output) if raw_output else 0} bytes'
            logger.error(f"[ESP-IDF Eval] {error_msg}")
            self.output_value = ''
            self.diagnostic_info = error_msg
            return False, error_msg
            
        self.output_value = raw_output
        logger.info(f"[ESP-IDF Eval] Using raw QEMU output for comparison (liberal matching)")
        logger.info(f"[ESP-IDF Eval] Total output file size: {len(self.output_value)} bytes")
            
        logger.info(f"[ESP-IDF Eval] Compilation successful")
        return True, None

    def check_code(self):
        # Compare output using liberal substring matching
        # Instead of exact match, check if expected output is contained in actual output
        # This is more practical for embedded systems where there's extra logging/noise
        
        def normalize(s):
            """Normalize by stripping whitespace from each line"""
            return '\n'.join(line.strip() for line in s.strip().splitlines() if line.strip())
        
        actual = normalize(self.output_value)
        expected = normalize(self.expected_output)
        
        # Liberal matching: check if each expected line appears somewhere in the actual output
        # This handles cases where there's extra logging/warnings
        is_correct = False
        if expected:
            expected_lines = expected.split('\n')
            actual_lines = actual.split('\n')
            
            # Check if all expected lines are present in actual output (order doesn't matter for now)
            is_correct = all(
                any(exp_line in act_line for act_line in actual_lines)
                for exp_line in expected_lines
            )
        else:
            # If no expected output, consider it correct if there's any output
            is_correct = bool(actual.strip())
        
        mark_fraction = self.weight
        
        logger.info(f"[ESP-IDF Eval] Output comparison (liberal substring matching):")
        logger.info(f"[ESP-IDF Eval] Expected output (normalized): {expected}")
        logger.info(f"[ESP-IDF Eval] Actual output (first 500 chars, normalized): {actual[:500]}")
        logger.info(f"[ESP-IDF Eval] Expected lines: {len(expected.split(chr(10)))}")
        logger.info(f"[ESP-IDF Eval] Actual lines: {len(actual.split(chr(10)))}")
        logger.info(f"[ESP-IDF Eval] Match result (substring contained): {is_correct}")
        
        if not is_correct:
            # Provide detailed diff info
            expected_lines = expected.split('\n')
            actual_lines = actual.split('\n')
            logger.warning(f"[ESP-IDF Eval] Expected {len(expected_lines)} lines, got {len(actual_lines)} lines")
            
            # Show which expected lines are missing
            for i, exp_line in enumerate(expected_lines):
                found = any(exp_line in act_line for act_line in actual_lines)
                if not found:
                    logger.warning(f"[ESP-IDF Eval] Expected line {i} NOT found in output: '{exp_line}'")
            
            if self.diagnostic_info:
                logger.warning(f"[ESP-IDF Eval] Diagnostic info: {self.diagnostic_info}")
        
        error_msg = None if is_correct else 'Expected output not found in actual output.'
        return is_correct, error_msg, mark_fraction
