# Define the function to perform arithmetic operations
def arithmetic_operations(a, b):
    # Addition
    addition = a + b
    
    # Subtraction
    subtraction = a - b
    
    # Multiplication
    multiplication = a * b
    
    # Division (handle division by zero)
    if b != 0:
        division = a / b
    else:
        division = "Division by zero is undefined"
    
    # Print all results
    print(f"Addition: {a} + {b} = {addition}")
    print(f"Subtraction: {a} - {b} = {subtraction}")
    print(f"Multiplication: {a} * {b} = {multiplication}")
    print(f"Division: {a} / {b} = {division}")

# Example usage
a = float(input("Enter the first number (a): "))
b = float(input("Enter the second number (b): "))

arithmetic_operations(a, b)