import sys
import inspect
from functools import wraps
from datetime import datetime

from flask import jsonify

from flask_yoloapi import utils
from flask_yoloapi.types import ANY

SUPPORTED_TYPES = (list, dict, datetime, None, ANY)
if sys.version_info >= (3, 0):
    NUMERIC_TYPES = (int, float)
    STRING_LIKE = (str,)

    SUPPORTED_TYPES += STRING_LIKE
    SUPPORTED_TYPES += NUMERIC_TYPES
else:
    STRING_LIKE = (unicode, str)
    NUMERIC_TYPES = (int, float, long)

    SUPPORTED_TYPES += STRING_LIKE
    SUPPORTED_TYPES += NUMERIC_TYPES


@utils.decorator_parametrized
def api(view_func, *parameters):
    """YOLO!"""
    messages = {
        "required": "argument '%s' is required",
        "type_error": "wrong type for argument '%s', "
                      "should be of type '%s'",
        "type_required_py3.5": "no type specified for parameter '%s', "
                               "specify a type argument or use "
                               "type annotations (PEP 484)",
        "bad_return": "view function returned unsupported type '%s'",
        "bad_return_tuple": "when returning tuples, the first index "
                            "must be an object of any supported "
                            "return type, the second a valid "
                            "HTTP return status code as an integer"
    }

    func_err = lambda ex, http_status=500: (jsonify(
        data=str(ex),
        docstring=utils.docstring(view_func, *parameters)
    ), http_status)

    @wraps(view_func)
    def validate_and_execute(*args, **kwargs):
        # grabs incoming data (multiple methods)
        request_data = utils.get_request_data()

        # fall-back type annotations from function signatures
        # when no parameter type is specified (python >3.5 only)
        type_annotations = None
        if sys.version_info >= (3, 5):
            signature = inspect.signature(view_func)
            type_annotations = {k: v.annotation for k, v in
                                signature.parameters.items()
                                if v.annotation is not inspect._empty}

        for param in parameters:
            # checks if param is required
            if param.key not in request_data:
                if param.required:
                    return func_err(messages["required"] % param.key)
                else:
                    # set default value, if provided
                    if param.default is not None:
                        kwargs[param.key] = param.default
                    else:
                        kwargs[param.key] = None
                    continue

            # set the param type from function annotation (runs only once)
            if type_annotations and param.type is None:
                if param.key in type_annotations:
                    param.type = type_annotations[param.key]
                else:
                    return func_err(messages["type_required_py3.5"] % param.key)

            # validate the param value
            value = request_data.get(param.key)
            if type(value) != param.type:
                if param.type in NUMERIC_TYPES:
                    try:
                        value = param.type(value)  # opportunistic coercing to int/float/long
                    except ValueError:
                        return func_err(messages["type_error"] % (param.key, param.type))
                elif param.type in STRING_LIKE:
                    pass
                elif param.type is ANY:
                    pass
                else:
                    return func_err(messages["type_error"] % (param.key, param.type))

            # validate via custom validator, if provided
            if param.kwargs.get('validator', None):
                try:
                    param.kwargs["validator"](value)
                except Exception as ex:
                    return func_err("parameter '%s' error: %s" % (param.key, str(ex)))

            kwargs[param.key] = value
        try:
            result = view_func(*args, **kwargs)
        except Exception as ex:
            return func_err("view function returned an error: %s" % str(ex))

        if result is None:
            return jsonify(data=None), 204

        # if view function returned a tuple, do http status code
        elif isinstance(result, tuple):
            if not len(result) == 2 or not isinstance(result[1], int):
                return func_err(messages["bad_return_tuple"])
            return jsonify(data=result[0]), result[1]

        elif not isinstance(result, SUPPORTED_TYPES):
            raise TypeError("Bad return type for api_result")

        return jsonify(data=result)
    return validate_and_execute


class parameter:
    def __init__(self, key, type=None, default=None, required=False, validator=None):
        if not isinstance(key, STRING_LIKE):
            raise TypeError("bad type for 'key'; must be 'str'")
        if not isinstance(required, bool):
            raise TypeError("bad type for 'required'; must be 'bool'")
        if type is not None:
            if type not in SUPPORTED_TYPES:
                raise TypeError("parameter type '%s' not supported" % str(type))
        else:
            if not sys.version_info >= (3, 0):
                raise TypeError("parameter with key '%s' missing 1 required argument: 'type'" % key)
        if default is not None and default.__class__ not in SUPPORTED_TYPES:
            raise TypeError("parameter default of type '%s' not supported" % str(type(default)))
        if validator is not None and not callable(validator):
            raise Exception("parameter 'validator' must be a function")

        self.kwargs = {"validator": validator}
        self.default = default
        self.key = str(key)
        self.type = type
        self.type_annotations = None
        self.required = required