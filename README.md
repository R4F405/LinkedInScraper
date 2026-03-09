# LinkedIn Scraper

Herramienta para descargar y visualizar datos de contactos de LinkedIn (conexiones de la cuenta con la que se inicia sesión).

## Vista web (recomendada)

La forma más sencilla de usar el proyecto es la interfaz web:

1. **Instalar dependencias** (si aún no lo has hecho):
   ```bash
   pip install -r requirements.txt
   ```

2. **Arrancar la app**:
   ```bash
   python app.py
   ```

3. **Abrir en el navegador**: [http://127.0.0.1:5001](http://127.0.0.1:5001)  
   (En macOS el puerto 5000 suele estar ocupado por AirPlay; por eso se usa 5001.)

### Qué puedes hacer en la vista

- **Nuevo scraping**: Pega la URL de un perfil de LinkedIn y pulsa «Iniciar scraping». Se abrirá una ventana de Terminal y Chrome para hacer login y descargar ese perfil.
- **Tus scrapeos**: Lista de todas las exportaciones (fecha y número de registros). Desde aquí puedes:
  - **Ver datos**: Ver la tabla de contactos en la página.
  - **Actualizar lista**: Refrescar la lista de scrapeos sin recargar la página.
  - **Exportar**: Descargar en **CSV** (verde), **Excel** (verde oscuro) o **PDF** (rojo).
- **En la tabla de datos** (al pulsar «Ver datos»):
  - **Buscar**: Escribe en el cuadro de búsqueda para filtrar por nombre, empresa, email, etc.
  - **Ordenar**: Haz clic en cualquier cabecera de columna para ordenar (asc/desc).
  - **Paginación**: Elige «Mostrar 10 / 25 / 50 / Todos» y ver el rango de filas mostrado.
  - **Resumen**: Se muestra cuántos contactos tienen email.
  - **Ocultar datos**: Botón para plegar el panel y volver a la lista.

### Si ves «Acceso denegado» a 127.0.0.1

Asegúrate de que la app está en marcha (`python app.py`) y escribe la URL a mano en la barra del navegador: `http://127.0.0.1:5001`.

## Uso por línea de comandos

- **Un solo perfil** (lo usa la vista web por debajo):
  ```bash
  python run_single.py "https://www.linkedin.com/in/nombre-perfil/"
  ```

- **Flujo completo** (perfil semilla → sus conexiones → scrapear todas): ver `run.py` y configurar las URLs en el código o en el archivo que use el script.

## Estructura del proyecto

- `app.py` — Servidor Flask y API de la vista web.
- `run_single.py` — Scraping de una URL (invocado por la vista o por terminal).
- `run.py` — Flujo: semilla → conexiones → scrapeo de todos los perfiles.
- `scraper/` — Login, driver Chrome, obtención de conexiones y perfiles.
- `parser/` — Extracción de datos desde el HTML guardado.
- `exporter/` — Exportación a CSV, Excel y PDF.
- `templates/` — Interfaz HTML/JS de la vista.
- `data/raw/` — HTML y JSON descargados.
- `data/output/` — CSV, Excel y PDF generados.

## Requisitos

Python 3.10+. Credenciales de LinkedIn en `.env` (ver `.env.example` si existe). Chrome instalado para el scraping con Selenium.
