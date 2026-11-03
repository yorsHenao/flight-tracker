"""
Archivo WSGI listo para configurar en la pestaña 'Web' de PythonAnywhere.
En PythonAnywhere, apunta el WSGI configuration file a:
    /home/tu_usuario/vuelos_tracker/wsgi.py
"""
import os
import sys

project_home = os.path.abspath(os.path.dirname(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import app as application  # noqa: E402
