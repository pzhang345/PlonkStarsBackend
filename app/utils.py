from random import randint

tolerance = 1e-7
def coord_at(model,num):
    return model.between(num - tolerance, num + tolerance)

def float_equals(num1,num2):
    return abs(num1 - num2) < tolerance

def generate_code(Party):
    code = None
    while not code or Party.query.filter_by(code=code).count():
        code = ""
        for _ in range(4):
            code += chr(randint(65, 90))
    return code