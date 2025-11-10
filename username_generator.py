import string

def generate_usernames():
    """
    A generator function that yields unique usernames based on specific patterns.
    You can customize the logic here to change the username patterns.

    Current Pattern: a_b_c, a_b_1, a_1_b, etc.
    (letter)_(letter/digit)_(letter/digit)
    """
    chars = string.ascii_lowercase
    chars_and_digits = string.ascii_lowercase + string.digits

    # Pattern: x_y_z
    # You can add more loops and different character sets to create more complex patterns.
    # For example, to generate four-character usernames like a_b_c_d, add another nested loop.

    for first_char in chars:
        for second_char in chars_and_digits:
            for third_char in chars_and_digits:
                yield f"{first_char}_{second_char}_{third_char}"

if __name__ == '__main__':
    # Example of how to use the generator
    print("Generating first 100 usernames as a test:")
    generator = generate_usernames()
    for i in range(100):
        try:
            print(next(generator))
        except StopIteration:
            print("--- End of usernames ---")
            break
