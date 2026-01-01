//file: main.cpp
#include "Arduino.h"

roc.stdout.decode('utf-8')
            error_msg = "Script failed with exit code {}.\nSTDERR:\n{}\nSTDOUT:\n{}".format(proc.returncode, stderr, stdout)
            with open(ino_file, 'w') as f:
                f.write(error_msg)
            return False, error_msg
