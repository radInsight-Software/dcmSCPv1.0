import sys
import os
import shutil
from setuptools import setup
from Cython.Build import cythonize

def convert_py_to_cython(py_file):
    if not py_file.endswith(".py"):
        print("Error: Please provide a valid Python file (.py)")
        return
    
    pyx_file = "main_protected.pyx"
    
    shutil.copy(py_file, pyx_file)
    print(f"Copied {py_file} to {pyx_file}")
    
    setup(
        ext_modules=cythonize(
            pyx_file,
            compiler_directives={
                "embedsignature": False,
                "language_level": "3",
                "boundscheck": False,  # Disables array bounds checking for performance
                "wraparound": False,   # Prevents negative indexing for better optimization
                "nonecheck": False,    # Disables NoneType checks to improve speed
            }
        ),
        script_args=['build_ext', '--inplace']
    )
    
    print(f"Compiled {pyx_file} successfully. Output: main_protected.so")
    
if __name__ == "__main__":
    
    pythonFile = "main.py"
    convert_py_to_cython(pythonFile)

