# Sistema de facturación · Flask

Este es un sistema de facturación desarrollado en **Python + Flask** con base de datos SQLite.  
Incluye gestión de clientes, productos, facturas y reportes básicos.

---

## 🚀 Requisitos

- Python 3.10 o superior
- SQLite (incluido en Python por defecto)
- Navegador web moderno

---

## ⚙️ Instalación

1. **Clonar el repositorio**

   git clone https://github.com/usuario/Flask-Trabajo.git
   cd Flask-Trabajo

2. **Crear un entorno virtual**

   python -m venv .venv

3. **Activar el entorno virtual**

   - **Windows (PowerShell)**
     .venv\Scripts\Activate.ps1
     ⚠️ Si aparece un error de ejecución de scripts (ExecutionPolicy):
     Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
     (Ejecutar como administrador la primera vez).

   - **Windows (CMD)**
     .venv\Scripts\activate.bat

   - **Linux / Mac**
     source .venv/bin/activate

4. **Instalar dependencias**

   pip install -r requirements.txt

5. **Ejecutar la aplicación**

   python app.py

   Se abrirá en: http://127.0.0.1:5000

---

## 🗄️ Base de datos

La base de datos se encuentra en la carpeta /instance como app.db.

- Reiniciar la base (conservar usuarios):

  python app.py resetdb

- Usuarios por defecto:
  - Administrador → administrador@facturas.com / admin
  - Usuario estándar → usuario@facturas.com / user

---

## 📌 Notas

- La carpeta /instance se crea automáticamente al ejecutar la aplicación si no existe.  
- No es necesario versionarla en Git (ya está en .gitignore).  
- Se recomienda siempre usar el entorno virtual para evitar conflictos de dependencias.

---

## 📜 Licencia

Este proyecto es de uso académico y libre para aprendizaje.
