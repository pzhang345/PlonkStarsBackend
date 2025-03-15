tolerance = 1e-9
def coord_at(model,num):
    return model.between(num - tolerance, num + tolerance)

def float_equals(num1,num2):
    return abs(num1 - num2) < tolerance