from random import randint

from flask import jsonify

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

def return_400_on_error(method,*args,**kwargs):
    try:
        ret = method(*args,**kwargs)
        if not ret:
            return jsonify(success=True),200
        
        if not isinstance(ret, tuple):
            return jsonify(ret),200
    except Exception as e:
        print(e)
        return jsonify({"error":str(e)}),400
    return jsonify(ret[0]),*ret[1:]