# Sistema de Revisión Acumulativa por Vuelta

## Descripción General

Este documento describe el nuevo sistema de revisión acumulativa de camas implementado en el módulo de fumigación. El sistema permite ajustar camas de manera iterativa entre vueltas, manteniendo los cambios anteriores como base para ajustes futuros.

## Problema Resuelto

**Antes:** Cuando se hacían ajustes de camas (quitar bloques, ajustar litrajes, etc.), estos se aplicaban de forma global a todas las vueltas seleccionadas mediante checkboxes. No había manera de hacer ajustes iterativos donde la vuelta 2 heredara los cambios de vuelta 1, y vuelta 3 heredara los cambios acumulados de vueltas 1 y 2.

**Ahora:** Cada vuelta puede tener sus propios ajustes que se construyen sobre los ajustes de vueltas anteriores. Cuando ajustas vuelta 2, automáticamente heredas los cambios de vuelta 1. Cuando ajustas vuelta 3, heredas los cambios acumulados de vueltas 1 y 2.

## Flujo de Trabajo del Usuario

### 1. Subir Estado de Cultivo
- Subir nuevo estado de cultivo con bloques recién podados/sembrados
- Estos bloques son los que se ajustarán en revisión y calibración de camas
- Esto evita duplicados y mantiene datos actualizados

### 2. Ajustar Primera Vuelta
1. Ir a Detalle de Rotación → Paso 2: Revisión y Calibración
2. Seleccionar "Vuelta 1" en el selector de radio
3. Hacer clic en "Cargar Camas de esta Vuelta"
4. Ajustar camas: quitar bloques, modificar litrajes, cambiar estados VEG/PROD
5. Guardar ajustes → Se guardan solo para Vuelta 1

### 3. Ajustar Segunda Vuelta (Acumulativo)
1. Seleccionar "Vuelta 2" en el selector de radio
2. Hacer clic en "Cargar Camas de esta Vuelta"
   - **Automáticamente carga los ajustes de Vuelta 1 como base**
3. Hacer ajustes adicionales sobre la base de Vuelta 1
4. Guardar ajustes → Se guardan solo para Vuelta 2 (pero incluyen herencia de Vuelta 1)

### 4. Ajustar Tercera Vuelta (Acumulativo)
1. Seleccionar "Vuelta 3" en el selector
2. Hacer clic en "Cargar Camas de esta Vuelta"
   - **Automáticamente carga los ajustes acumulados de Vueltas 1 y 2**
3. Hacer ajustes adicionales sobre la base acumulada
4. Guardar ajustes → Se guardan solo para Vuelta 3

## Arquitectura Técnica

### Base de Datos

#### Nuevo Campo
```python
# models.py - Rotation class
review_data_by_round_json = db.Column(db.Text, nullable=True)
# Formato: {"round_id": [segments], "another_round_id": [segments], ...}
```

#### Campos Deprecados (mantener por compatibilidad)
```python
review_data_json = db.Column(db.Text)  # DEPRECATED
applied_rounds_json = db.Column(db.Text)  # DEPRECATED
```

### Endpoints Backend

#### 1. Guardar Revisión por Vuelta
```python
POST /rotaciones/<rotation_id>/guardar-revision
Body: {
    "target_round_id": 123,
    "segments": [...]
}
```
- Recibe solo UNA vuelta objetivo
- Guarda segmentos para esa vuelta específica
- Formato en DB: `{"123": [...segments...], "124": [...segments...]}`

#### 2. Obtener Datos Acumulativos
```python
GET /rotaciones/<rotation_id>/get-cumulative?round_id=124
Response: {
    "success": true,
    "round_name": "Vuelta 2",
    "segments": [...]
}
```
- Calcula segmentos acumulativos hasta la vuelta solicitada
- Aplica ajustes de todas las vueltas anteriores en orden

#### 3. Generar Orden de Fumigación
```python
POST /rotaciones/generar-orden/<round_id>
```
- Busca en `review_data_by_round_json` los ajustes acumulativos
- Aplica la última versión disponible hasta esa vuelta
- Genera orden congelada con esos datos

### Frontend (rotacion_detalle.html)

#### Interfaz de Usuario
```html
<!-- Selector de Vuelta Objetivo (Radio Buttons) -->
<div class="card mb-3 shadow-sm border-warning">
    <div class="card-header bg-warning text-dark">
        ¿Para qué vuelta estás haciendo estos ajustes?
    </div>
    <div class="card-body">
        <!-- Radio buttons para cada vuelta -->
        <input type="radio" name="target_round" value="round_id">
        
        <!-- Botón para cargar datos acumulativos -->
        <button id="btn-load-cumulative">
            Cargar Camas de esta Vuelta
        </button>
        
        <!-- Alerta explicativa -->
        <div class="alert alert-warning">
            Lógica acumulativa: Al ajustar vuelta 2, se cargan 
            automáticamente los cambios de vuelta 1.
        </div>
    </div>
</div>
```

#### Lógica JavaScript
```javascript
// Al hacer clic en "Cargar Camas de esta Vuelta"
document.getElementById('btn-load-cumulative').addEventListener('click', function() {
    const targetRoundId = document.querySelector('.round-target-radio:checked').value;
    
    // Fetch datos acumulativos
    fetch(`/rotaciones/${rotation_id}/get-cumulative?round_id=${targetRoundId}`)
        .then(response => response.json())
        .then(data => {
            // Limpiar tabla
            tbody.innerHTML = '';
            
            // Llenar con segmentos acumulativos
            data.segments.forEach(seg => addRowToCleanTable(seg));
        });
});

// Al guardar ajustes
document.getElementById('btn-save-clean-review').addEventListener('click', function() {
    const targetRoundId = document.querySelector('.round-target-radio:checked').value;
    
    // Recopilar segmentos de la tabla
    const segments = collectSegmentsFromTable();
    
    // Enviar al backend
    fetch('/rotaciones/${rotation_id}/guardar-revision', {
        method: 'POST',
        body: JSON.stringify({
            target_round_id: targetRoundId,
            segments: segments
        })
    });
});
```

## Ejemplo de Flujo de Datos

### Escenario: Rotación con 3 vueltas

#### Estado Inicial (Sin Ajustes)
```json
{
  "review_data_by_round_json": null
}
```
- Todas las vueltas usan cálculo base del motor

#### Después de Ajustar Vuelta 1
```json
{
  "review_data_by_round_json": {
    "101": [
      {"zone": "A1", "block": "01", "beds": 50, "liters": 10},
      {"zone": "A1", "block": "02", "beds": 45, "liters": 10}
    ]
  }
}
```
- Vuelta 1 (ID 101): Usa configuración custom
- Vuelta 2 y 3: Usan cálculo base

#### Después de Ajustar Vuelta 2
```json
{
  "review_data_by_round_json": {
    "101": [
      {"zone": "A1", "block": "01", "beds": 50, "liters": 10},
      {"zone": "A1", "block": "02", "beds": 45, "liters": 10}
    ],
    "102": [
      {"zone": "A1", "block": "01", "beds": 50, "liters": 10},
      {"zone": "A1", "block": "02", "beds": 40, "liters": 9}
    ]
  }
}
```
- Vuelta 1: Configuración original
- Vuelta 2 (ID 102): Heredó vuelta 1, pero redujo camas del bloque 02 de 45→40 y litraje de 10→9
- Vuelta 3: Usa herencia acumulativa de vueltas 1 y 2

#### Lógica de Aplicación
Cuando se genera orden para Vuelta 3 (ID 103):
1. No hay entrada para "103" en el diccionario
2. Sistema busca hacia atrás: ¿Hay "102"? Sí → usa esos segmentos
3. Esos segmentos ya incluyen herencia de "101"

## Ventajas del Sistema

### 1. Ajustes Iterativos
- Cada vuelta construye sobre la anterior
- No necesitas repetir ajustes en cada vuelta
- Más natural para el flujo de trabajo del agrónomo

### 2. Independencia por Vuelta
- Cada vuelta puede tener su configuración única
- Fácil rastrear qué cambios se hicieron en qué vuelta
- Auditoría clara de ajustes por vuelta

### 3. Flexibilidad
- Puedes volver a ajustar cualquier vuelta en cualquier momento
- Los cambios solo afectan a esa vuelta y las posteriores
- No se rompe la cadena de herencia

### 4. Datos Limpios
- Un solo campo JSON con estructura clara
- No más "applied_rounds" confusos
- Fácil de exportar y auditar

## Migración desde Sistema Antiguo

### Campos Deprecados
Los siguientes campos se mantienen por compatibilidad pero NO se usan:
- `review_data_json`: Single JSON con configuración global
- `applied_rounds_json`: Array de IDs de vueltas donde aplicar

### Migración Automática
El sistema migra automáticamente:
1. Si existe `review_data_json` pero no `review_data_by_round_json`
2. Sistema usa datos antiguos como fallback
3. Al guardar nuevos ajustes, se usa nuevo sistema

### Script de Migración
```bash
py migrate_db.py
```
Agrega columna `review_data_by_round_json` a tabla `rotations`

## Testing del Sistema

### Test Manual
1. **Crear nueva rotación** con 3 vueltas
2. **Ajustar Vuelta 1**: Quitar 2 bloques, reducir litraje de 10→8
3. **Verificar guardado**: Check DB que existe entrada para vuelta 1
4. **Cargar Vuelta 2**: Debe mostrar configuración de vuelta 1
5. **Ajustar Vuelta 2**: Quitar 1 bloque más
6. **Verificar guardado**: Check DB que existe entrada para vuelta 2
7. **Cargar Vuelta 3**: Debe mostrar configuración acumulada (vueltas 1+2)
8. **Generar orden vuelta 2**: Verificar que usa datos correctos
9. **Generar orden vuelta 3**: Verificar que usa datos acumulados

### Casos de Borde
- ✅ Vuelta sin ajustes previos → usa cálculo base
- ✅ Primera vuelta → no hereda nada
- ✅ Vuelta intermedia sin ajuste explícito → hereda anterior más cercana
- ✅ Re-ajustar vuelta 1 → no afecta vueltas ya guardadas (2, 3)
- ✅ Eliminar vuelta 2 → vuelta 3 hereda de vuelta 1

## Mantenimiento Futuro

### Agregar Nueva Vuelta
- Sistema automáticamente hereda última configuración disponible
- No requiere código adicional

### Cambiar Orden de Vueltas
- Asegurar que `RotationRound.round_number` está correcto
- Sistema usa este campo para determinar herencia

### Eliminar Vuelta
- Si eliminas vuelta intermedia, vueltas posteriores heredan de anterior disponible
- No requiere limpieza manual de datos

## Referencias de Código

### Archivos Modificados
1. `app/shared/models.py` - Línea ~229: Campo `review_data_by_round_json`
2. `migrate_db.py` - Línea ~180: Migración de nueva columna
3. `app/modules/fumigacion/routes.py`:
   - Línea ~255: `rotacion_detalle()` - Carga datos acumulativos
   - Línea ~337: `rotacion_guardar_revision()` - Guarda por vuelta
   - Línea ~370: `rotacion_get_cumulative()` - Calcula acumulativo
   - Línea ~420: `generar_orden()` - Usa datos acumulativos
4. `app/templates/fumigacion/rotacion_detalle.html`:
   - Línea ~285: Selector de vuelta objetivo
   - Línea ~765: JavaScript para cargar acumulativo
   - Línea ~820: JavaScript para guardar por vuelta

### Dependencias
- Flask (routing, JSON)
- SQLAlchemy (models, queries)
- JavaScript (frontend logic)
- Bootstrap 5 (UI components)

## Soporte y Troubleshooting

### Problema: No se cargan datos acumulativos
**Solución:** 
- Verificar que `review_data_by_round_json` existe en DB
- Check logs del servidor para errores de parsing JSON
- Verificar que round_id está en el diccionario

### Problema: Los ajustes no se guardan
**Solución:**
- Verificar que se seleccionó una vuelta objetivo (radio button)
- Check que segments no está vacío
- Verificar permisos de escritura en DB

### Problema: Orden generada tiene datos incorrectos
**Solución:**
- Verificar lógica acumulativa en `generar_orden()`
- Check que round_ids_ordered está correcto
- Verificar que custom_segs se aplica correctamente

## Contacto
Para preguntas o mejoras, contactar al equipo de desarrollo.
