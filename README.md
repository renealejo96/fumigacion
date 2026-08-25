# AgroFumigación - Plataforma de Gestión Agrícola y Fumigación

Plataforma web modular, escalable y robusta desarrollada en **Python y Flask** para la gestión fitosanitaria y planificación de rotaciones de fumigación en fincas florícolas.

---

## 🚀 Características Principales

### 1. Cuatro Supermódulos Agrícolas
* **1. Fumigación (Completamente Desarrollado):**
  * Planificación de rotaciones semanales por cultivo y estado fenológico (Vegetativo vs Productivo).
  * Vueltas dinámicas e ilimitadas (Vuelta 1, Vuelta 2, Vuelta 3, etc.) con día programado configurable (Lunes, Jueves, u otros).
  * Selección asistida de agroquímicos con autocompletado y búsqueda desde el catálogo.
  * Extracción automática de dosis configuradas (`dosis_fumi`) y unidades de medida (`CC`, `GR`, `KG`, `LT`).
  * Simulación en tiempo real y cálculo automático de:
    * Segmentación exacta de camas por bloque, sufijo y edad real.
    * Suma de camas estándar.
    * Litros requeridos según la matriz de litrajes por cultivo y edad.
    * Cantidad total de cada producto a preparar.
    * Resumen consolidado para bodega y preparación de mezcla en tanque.
  * Generación y congelamiento de **Órdenes de Fumigación Inmutables** con vista optimizada para impresión en campo (`@media print`), firmas y control de ejecución.
* **2. Drench (Estructura Base / Carcasa Modular):** Preparado arquitectónicamente para nutrición y fungicidas de suelo con soporte para `dosis drench`.
* **3. Trichos (Estructura Base / Carcasa Modular):** Preparado para la gestión de inoculación y control biológico con *Trichoderma spp.*
* **4. Desinfecciones (Estructura Base / Carcasa Modular):** Preparado para desinfección de camas, suelos, reservorios de agua y poscosecha.

---

### 2. Catálogos y Módulos Administrativos
* **Catálogo de Productos y Dosis:** CRUD completo, búsqueda por código corto, nombre comercial, plaga e ingrediente activo, dosis foliar y drench, estado activo/inactivo.
* **Cultivos y Rangos de Edad:** Configuración editable de rangos de edad en semanas para clasificar automáticamente las camas en Vegetativo o Productivo (ej. Hypericum 0-12 veg / 13-25 prod; Veronica, Solidago, Gypsophila 0-9 veg / 10-15+ prod).
* **Matriz de Litrajes:** Consulta y edición de litros por cama estándar según cultivo y edad.
* **Estado de Cultivo y Explorador de Camas:** Visualización de camas físicas y segmentación agrupada por bloque, sufijo, variedad y edad.
* **Importador y Normalizador de Excel:**
  * Tolerancia a variaciones en encabezados (mayúsculas, minúsculas, tildes, espacios y caracteres especiales).
  * Soporte para `Estado Cultivo PYGAN 2026-33.xlsx` (lectura desde fila 5 en hoja `DATOS`), `productos y dosis.xlsx` y `litrajes.xlsx`.
  * Previsualización de datos antes de guardar y registro de auditoría de lotes importados.
* **Trazabilidad y Auditoría:** Registro histórico de cambios en rotaciones, órdenes, dosis y catálogos.

---

## 📂 Arquitectura del Proyecto

```text
fumigacion/
├── app/
│   ├── __init__.py                # App factory y registro de blueprints
│   ├── config.py                  # Configuración (SQLite/PostgreSQL, uploads)
│   ├── extensions.py              # Instancia de base de datos SQLAlchemy
│   ├── modules/
│   │   ├── fumigacion/            # MÓDULO PRINCIPAL FUMIGACIÓN
│   │   │   ├── routes.py          # Rutas de Rotaciones y Órdenes
│   │   │   └── services/
│   │   │       ├── calculation_engine.py  # Motor de cálculo y segmentación
│   │   │       └── order_service.py       # Generador de órdenes congeladas
│   │   ├── drench/                # Carcasa modular Drench
│   │   ├── trichos/               # Carcasa modular Trichos
│   │   ├── desinfecciones/        # Carcasa modular Desinfecciones
│   │   ├── productos/             # Catálogo de Productos y Dosis
│   │   ├── cultivos/              # Configuración de Cultivos y Rangos de Edad
│   │   ├── litrajes/              # Matriz de Litrajes por Cama
│   │   ├── estado_cultivo/        # Explorador de Camas y Segmentos
│   │   └── importador/            # Importador y Validador Excel
│   ├── shared/
│   │   ├── models.py              # Modelos de base de datos normalizados
│   │   ├── normalizer.py          # Limpiador y mapeador tolerante de encabezados
│   │   ├── excel_parser.py        # Lectores especializados para los 3 archivos Excel
│   │   └── audit.py               # Servicio de registro de auditoría
│   ├── static/
│   │   └── css/main.css           # Estilos agrícolas modernos y @media print
│   └── templates/                 # Plantillas Jinja2 organizadas por módulo
├── tests/
│   ├── test_normalizer.py         # Pruebas de normalización de encabezados
│   ├── test_age_ranges.py         # Pruebas de clasificación fenológica
│   ├── test_segmentation.py       # Pruebas de segmentación por sufijo y cama
│   ├── test_calculations.py       # Pruebas de fórmulas y órdenes inmutables
│   └── test_excel_importers.py    # Pruebas de lectura de archivos Excel
├── seed_data.py                   # Poblador inicial automático de la base de datos
├── run.py                         # Punto de entrada para ejecutar el servidor
├── productos y dosis.xlsx         # Archivo fuente inicial
├── litrajes.xlsx                  # Archivo fuente inicial
└── Estado Cultivo PYGAN 2026-33.xlsx # Archivo fuente inicial
```

---

## 🛠️ Instalación y Ejecución

### 1. Requisitos
* Python 3.10+
* Librerías: `Flask`, `Flask-SQLAlchemy`, `pandas`, `openpyxl`

### 2. Inicializar Base de Datos con Datos Reales
Ejecuta el script de carga inicial:
```bash
python seed_data.py
```
Este script creará la base de datos SQLite `fumigacion_agricola.db` e importará automáticamente los 507 productos, las 215 reglas de litrajes y las 9,129 camas de cultivo desde los archivos fuente disponibles.

### 3. Ejecutar la Aplicación Web
```bash
python run.py
```
Abre tu navegador en:
👉 **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🧪 Ejecución de Pruebas Automatizadas

Para ejecutar la suite completa de pruebas unitarias y de integración:
```bash
python -m unittest discover -s tests
```

---

## 📋 Lógica de Negocio y Fórmulas Aplicadas

1. **Segmento de Aplicación:**
   $$\text{Segmento} = (\text{Bloque}, \text{Sufijo}, \text{Cultivo}, \text{Edad Real}, \text{Zona})$$
2. **Camas Estándar del Segmento:**
   $$\text{Camas Estándar} = \sum_{\text{camas en segmento}} \text{cama\_estandar}$$
3. **Litros Totales del Segmento:**
   $$\text{Litros Totales} = \text{Camas Estándar} \times \text{Litraje}(\text{Cultivo}, \text{Edad})$$
4. **Cantidad de Agroquímico por Segmento:**
   $$\text{Cantidad Producto} = \text{Litros Totales} \times \text{Dosis Fumigación}$$
5. **Consolidado de Producto para Tanque:**
   $$\text{Total Producto} = \sum_{\text{todos los segmentos}} \text{Cantidad Producto}$$

---

## 🐳 Despliegue con Docker y PostgreSQL en VPS (Hostinger)

### 📌 Puertos Configurados (Sin colisión con servicios existentes)
* **Aplicación Web (Gunicorn / Flask):** Puerto Host `8095` $\rightarrow$ Contenedor `5000` (`http://<TU_IP_VPS>:8095`)
* **Base de Datos PostgreSQL:** Puerto Host `5495` $\rightarrow$ Contenedor `5432`

### 🚀 Pasos para desplegar en el VPS:
1. Clonar el repositorio en el VPS:
   ```bash
   git clone https://github.com/renealejo96/fumigacion.git
   cd fumigacion
   ```
2. Crear el archivo `.env` a partir del ejemplo:
   ```bash
   cp .env.example .env
   ```
3. Iniciar los contenedores:
   ```bash
   docker compose up -d --build
   ```
4. El contenedor inicializará automáticamente la base de datos PostgreSQL, creará las tablas y el usuario administrador inicial (`admin` / `admin123`).

