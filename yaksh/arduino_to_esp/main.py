from tree_sitter import Parser, Language
import tree_sitter_cpp
import sys
import csv

# -------------------------------
# 1. Setup Tree-sitter for C++
# -------------------------------

CPP_LANGUAGE = Language(tree_sitter_cpp.language())

parser = Parser()
parser.language = CPP_LANGUAGE


# -------------------------------
# 2. Find digitalWrite() calls
# -------------------------------

def find_digital_write_calls(node, source, results):
    if node.type == "call_expression":
        fn = node.child_by_field_name("function")
        if fn:
            name = source[fn.start_byte:fn.end_byte].decode()
            if name == "digitalWrite":
                results.append(node)

    for child in node.children:
        find_digital_write_calls(child, source, results)


def find_function_calls(node, source, func_name, results):
    if node.type == "call_expression":
        fn = node.child_by_field_name("function")
        if fn:
            name = source[fn.start_byte:fn.end_byte].decode()
            if name == func_name:
                results.append(node)
    for child in node.children:
        find_function_calls(child, source, func_name, results)


# -------------------------------
# 3. Extract arguments
# -------------------------------

def extract_args(call_node, source):
    args = call_node.child_by_field_name("arguments")
    values = []

    for child in args.children:
        if child.type not in ("(", ")", ","):
            values.append(
                source[child.start_byte:child.end_byte].decode().strip()
            )

    return values  # [pin, value]


def extract_variable_assignments(tree, source):
    assignments = {}
    # Traverse the tree to find variable assignments
    def visit(node):
        if node.type == "declaration":
            # Look for int var = value;
            var_type = node.child_by_field_name("type")
            var_name = node.child_by_field_name("declarator")
            var_value = None
            if var_name:
                # Check for assignment
                for child in node.children:
                    if child.type == "init_declarator":
                        # Should have '=' and value
                        for subchild in child.children:
                            if subchild.type == "number_literal" or subchild.type == "identifier" or subchild.type == "field_identifier":
                                var_value = source[subchild.start_byte:subchild.end_byte].decode().strip()
                            elif subchild.type == "assignment_expression":
                                # assignment_expression: left, '=', right
                                right = subchild.child_by_field_name("right")
                                if right:
                                    var_value = source[right.start_byte:right.end_byte].decode().strip()
                var_name_str = source[var_name.start_byte:var_name.end_byte].decode().strip()
                if var_value:
                    assignments[var_name_str] = var_value
        for child in node.children:
            visit(child)
    visit(tree.root_node)
    return assignments


# -------------------------------
# 4. Main
# -------------------------------

ANALOG_PINS = {"A0", "A1", "A2", "A3", "A4", "A5", 0, 1, 2, 3, 4, 5}
DIGITAL_PINS = {f"D{i}" for i in range(14)} | set(range(14))


def is_valid_pin(func, pin):
    # Accept both string and integer representations
    if func == "analogRead":
        return pin in ANALOG_PINS
    if func in ("digitalRead", "digitalWrite"):
        return pin in DIGITAL_PINS
    return True


def parse_pin_list(pin_arg):
    pin_arg = pin_arg.strip()
    if pin_arg.startswith('[') and pin_arg.endswith(']'):
        pin_arg = pin_arg[1:-1]
    pins = [int(x.strip()) for x in pin_arg.split(',') if x.strip()]
    return set(pins)


def main():
    if len(sys.argv) < 4:
        print("Usage: python main.py <input.ino> <output.ino> <check.csv>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]
    csv_file = sys.argv[3]

    source = open(input_file, "rb").read()
    tree = parser.parse(source)
    var_assignments = extract_variable_assignments(tree, source)

    # Instrument digitalWrite as before
    calls = []
    find_digital_write_calls(tree.root_node, source, calls)
    edits = []
    for call in calls:
        args = extract_args(call, source)
        pin, val = args[:2] if len(args) >= 2 else (None, None)
        # Resolve pin if it's a variable
        if pin in var_assignments:
            pin_resolved = var_assignments[pin]
        else:
            pin_resolved = pin
        log_stmt = (
            f'ESP_LOGI(TAG, "PIN {pin_resolved}, {val}");'
        ).encode()
        edits.append(
            (call.start_byte, call.end_byte, log_stmt)
        )
    instrumented = bytearray(source)
    for start, end, repl in sorted(edits, reverse=True):
        instrumented[start:end] = repl
    with open(output_file, "wb") as f:
        f.write(instrumented)
    print(f"[OK] Written instrumented file: {output_file}")

    # Check CSV for function/pin presence
    with open(csv_file, newline='') as csvfile:
        reader = csv.reader(csvfile)
        # Skip header row (pin_type, pin_number)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            func, pin = row[0].strip(), row[1].strip()
            # Try to convert pin to int if possible, else keep as string
            try:
                pin_val = int(pin)
            except ValueError:
                pin_val = pin
            func_calls = []
            find_function_calls(tree.root_node, source, func, func_calls)
            pins_used = set()
            for call in func_calls:
                args = extract_args(call, source)
                arg_pin = args[0] if args else None
                # Resolve variable if needed
                if arg_pin in var_assignments:
                    arg_pin_val = var_assignments[arg_pin]
                    try:
                        arg_pin_val = int(arg_pin_val)
                    except ValueError:
                        pass
                else:
                    try:
                        arg_pin_val = int(arg_pin)
                    except (ValueError, TypeError):
                        arg_pin_val = arg_pin
                pins_used.add(str(arg_pin_val))
            if str(pin_val) in pins_used:
                print(f"[FOUND] {func}({pin}) is present in the code.")
            elif pins_used:
                print(f"[PRESENT] {func} is used, but with different pin(s): {', '.join(sorted(pins_used))}")
            else:
                print(f"[MISSING] {func}({pin}) is NOT present in the code.")


if __name__ == "__main__":
    main()
