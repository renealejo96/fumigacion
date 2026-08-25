# Sistema de Presupuesto y Aprobación de Órdenes de Compra

## 📋 Descripción General

Esta funcionalidad permite **inflar las camas** de la orden de compra con proyecciones de presupuesto cuando el plano de cultivo está desactualizado. Es especialmente útil cuando:

- El plano disponible es de semana N-1 o anterior
- Hubo siembras o podas recientes que no aparecen en el plano
- Necesitas planificar compras para bloques que aún no están registrados

> ⚠️ **IMPORTANTE**: Esta es la funcionalidad más crítica del negocio. Sin los ajustes de presupuesto, la orden de compra estará incompleta y faltarán productos al momento de la aplicación.

---

## 🎯 Problema que Resuelve

**Escenario típico:**
1. Hoy es semana 34
2. El plano disponible es de semana 33
3. Estás planificando la rotación para semana 35
4. En semana 33 se sembraron 50 camas de MOONWALK de 2 semanas
5. Esas 50 camas NO aparecen en el plano de semana 33 porque apenas se sembraron

**Sin ajustes de presupuesto:**
- La orden de compra NO incluye productos para esas 50 camas
- Faltarán productos al momento de fumigar
- No puedes aprobar el pedido porque sabes que está incompleto

**Con ajustes de presupuesto:**
- Agregas manualmente: "50 camas de MOONWALK, 2 semanas, VEGETATIVO"
- El sistema recalcula la orden sumando las camas de presupuesto
- La orden de compra refleja la realidad completa
- Puedes aprobar el pedido con confianza

---

## 🛠️ Componentes Implementados

### 1. Campos de Base de Datos

**Tabla `requisitions`:**
```sql
- budget_adjustments_json (TEXT): JSON con ajustes de presupuesto
  Formato: [{"crop_name": "MOONWALK", "age": 2, "stage": "VEGETATIVO", "beds": 50, "reason": "Siembras semana 33"}, ...]

- approved_by (VARCHAR(100)): Usuario que aprobó la orden
- approved_at (DATETIME): Fecha/hora de aprobación
- status (VARCHAR(30)): Estado de la requisición
  Valores: 'PENDIENTE', 'APROBADO', 'VALIDADO'
```

### 2. Interfaz de Usuario

**Ubicación:** Orden de Compra → `/orden-compra`

**Nueva sección: "Ajustes de Presupuesto"**
- Card con borde amarillo (destaca visualmente)
- Tabla para agregar camas adicionales
- Campos por fila:
  - Cultivo/Variedad (con autocompletado)
  - Edad (semanas)
  - Estado fenológico (VEGETATIVO/PRODUCTIVO)
  - Camas Presupuesto (número decimal)
  - Motivo (texto libre, ej: "Siembras semana 33")
- Botón "Agregar Fila de Presupuesto"
- Botón "Recalcular Pedido con Presupuesto" (amarillo, destacado)

**Estado de aprobación:**
- Badge en header de requisición:
  - 🟡 PENDIENTE (amarillo)
  - 🟢 APROBADO (verde con check)
- Botón "Aprobar Orden" (solo visible si status=PENDIENTE)

### 3. Backend - Endpoints

**`POST /orden-compra/recalculate-with-budget`**
- Guarda los ajustes de presupuesto en `budget_adjustments_json`
- Recalcula la requisición sumando camas configuradas + camas de presupuesto
- Retorna JSON: `{success: true, message: "..."}`

**`POST /orden-compra/approve-order`**
- Cambia status de PENDIENTE → APROBADO
- Registra `approved_by` y `approved_at`
- Retorna JSON: `{success: true, message: "..."}`

### 4. Lógica de Recálculo

**Archivo:** `app/modules/fumigacion/services/requisition_service.py`

**Método:** `recalculate_with_budget(requisition_id, budget_adjustments)`

**Proceso:**
1. Calcula base desde rondas de rotación (igual que antes)
2. Para cada ajuste de presupuesto:
   - Busca litraje por cultivo/edad (default: 80L/cama)
   - Calcula litros totales: `beds × liters_per_bed`
   - Obtiene productos de la rotación para ese cultivo/estado
   - Calcula cantidades adicionales: `(dosis × litros_budget) / 100`
   - Suma a los totales de productos
3. Actualiza RequisitionItem con totales finales
4. Actualiza `total_liters` de requisición

---

## 📖 Flujo de Uso

### Paso 1: Seleccionar Semana
1. Ir a **Orden de Compra** en el menú lateral
2. Seleccionar la semana objetivo (ej: 2026-35)
3. Verificar que exista una rotación para esa semana
4. El sistema muestra la configuración de camas actual

### Paso 2: Agregar Camas de Presupuesto
1. Scroll hacia abajo hasta "Ajustes de Presupuesto"
2. Click en **"Agregar Fila de Presupuesto"**
3. Completar datos:
   - **Cultivo:** Ej: MOONWALK (con autocompletado)
   - **Edad:** Ej: 2
   - **Estado:** VEGETATIVO (para siembras recientes)
   - **Camas:** Ej: 50
   - **Motivo:** Ej: "Siembras semana 33 Bloque 3-4"
4. Agregar más filas según sea necesario

### Paso 3: Recalcular Pedido
1. Click en **"Recalcular Pedido con Presupuesto"**
2. El sistema:
   - Guarda los ajustes en la base de datos
   - Recalcula productos sumando camas configuradas + presupuesto
   - Actualiza la tabla "Requisición Calculada"
3. Verificar que las cantidades reflejen las camas adicionales

### Paso 4: Aprobar Orden
1. Revisar la requisición calculada
2. Verificar que todos los productos necesarios estén incluidos
3. Click en **"Aprobar Orden"**
4. Confirmar en el diálogo
5. El sistema:
   - Cambia estado a APROBADO
   - Muestra badge verde
   - Registra usuario y fecha de aprobación

### Paso 5: Exportar a Excel (opcional)
1. Click en "Exportar a Excel"
2. Se descarga el archivo con la orden de compra completa

---

## 💡 Casos de Uso Comunes

### Caso 1: Siembras Recientes
```
Situación: Sembré 100 camas de MOONWALK hace 2 semanas
Solución:
- Cultivo: MOONWALK
- Edad: 2
- Estado: VEGETATIVO
- Camas: 100
- Motivo: "Siembra semana 32 Bloque 15"
```

### Caso 2: Podas Recientes
```
Situación: Podé 75 camas de TANGO que pasaron de 50 a 3 semanas
Solución:
- Cultivo: TANGO
- Edad: 3
- Estado: VEGETATIVO
- Camas: 75
- Motivo: "Poda rejuvenecimiento semana 33"
```

### Caso 3: Bloques Proyectados
```
Situación: Van a sembrar 120 camas de CAMAROSA esta semana
Solución:
- Cultivo: CAMAROSA
- Edad: 1
- Estado: VEGETATIVO
- Camas: 120
- Motivo: "Siembra programada semana 34"
```

---

## 🔍 Verificación y Validación

### Cómo verificar que funciona correctamente:

1. **Sin presupuesto:**
   - Ir a Orden de Compra
   - Anotar las cantidades de productos

2. **Agregar presupuesto:**
   - Agregar 50 camas de un cultivo vegetativo
   - Recalcular

3. **Verificar:**
   - Las cantidades de productos deben AUMENTAR
   - El aumento debe ser proporcional a: `(dosis × 50_camas × litraje) / 100`
   - Ej: Si MOONWALK usa 80L/cama y un producto al 0.3%:
     - Litros adicionales: 50 × 80 = 4000L
     - Cantidad adicional: (0.3 × 4000) / 100 = 12 unidades

4. **Persistencia:**
   - Recargar la página
   - Las filas de presupuesto deben seguir ahí
   - Las cantidades calculadas deben mantenerse

---

## ⚙️ Configuración Técnica

### Migración de Base de Datos

**Archivo:** `migrate_db.py`

El script de migración ya ejecutado agregó:
```python
# Agregar columnas a requisitions
ALTER TABLE requisitions ADD COLUMN budget_adjustments_json TEXT;
ALTER TABLE requisitions ADD COLUMN approved_by VARCHAR(100);
ALTER TABLE requisitions ADD COLUMN approved_at DATETIME;

# Actualizar status existentes
UPDATE requisitions SET status = 'PENDIENTE' WHERE status = 'PEDIDO_INICIAL';
```

### Dependencias

- **Frontend:** Bootstrap 5.3.3, FontAwesome 6.5.1, JavaScript ES6
- **Backend:** Flask, SQLAlchemy, SQLite
- **Formato JSON:** Arrays y objetos en columnas TEXT

---

## 🐛 Troubleshooting

### Problema: No se recalcula al agregar presupuesto
**Solución:** Verificar que hay al menos una fila de presupuesto completada antes de hacer click en "Recalcular"

### Problema: Las camas de presupuesto no aparecen al recargar
**Solución:** 
- Verificar que se hizo click en "Recalcular Pedido"
- Verificar que `budget_adjustments_json` tiene datos en la BD:
```sql
SELECT id, week, budget_adjustments_json FROM requisitions WHERE week = '2026-35';
```

### Problema: No puedo aprobar la orden
**Solución:**
- Verificar que el status sea 'PENDIENTE'
- Verificar que existe una requisición para esa semana
- Revisar errores en consola del navegador (F12)

### Problema: Las cantidades no aumentan al agregar presupuesto
**Solución:**
- Verificar que el cultivo agregado tiene productos asignados en la rotación
- Verificar que el litraje del cultivo/edad existe en tabla `litrajes`
- Revisar logs del servidor para errores de cálculo

---

## 📊 Ejemplo Completo

### Configuración Inicial
- Rotación semana 2026-35
- Camas configuradas (del plano): 100 camas de MOONWALK de 10 semanas (PRODUCTIVO)
- Productos en rotación: SWITCH SC al 0.3%, SCORE SC al 0.2%

### Cálculo Base (sin presupuesto)
- Litraje MOONWALK 10 sem: 120 L/cama
- Total litros: 100 × 120 = 12,000 L
- SWITCH: (0.3 × 12,000) / 100 = 36 L
- SCORE: (0.2 × 12,000) / 100 = 24 L

### Agregar Presupuesto
- Cultivo: MOONWALK
- Edad: 2 semanas
- Estado: VEGETATIVO
- Camas: 50
- Motivo: "Siembras semana 33"

### Cálculo con Presupuesto
- Litraje MOONWALK 2 sem: 80 L/cama
- Litros adicionales: 50 × 80 = 4,000 L
- Total litros: 12,000 + 4,000 = 16,000 L
- SWITCH adicional: (0.3 × 4,000) / 100 = 12 L → **Total: 48 L**
- SCORE adicional: (0.2 × 4,000) / 100 = 8 L → **Total: 32 L**

### Resultado Final
- Orden de compra APROBADA con 48L de SWITCH y 32L de SCORE
- Usuario puede proceder con confianza
- Productos suficientes para las 150 camas reales (100 + 50)

---

## 🚀 Próximas Mejoras

### En Consideración:
- [ ] Validación automática contra stock disponible
- [ ] Historial de aprobaciones con comentarios
- [ ] Exportar PDF de orden aprobada
- [ ] Notificaciones por email al aprobar
- [ ] Comparativa presupuesto vs real post-aplicación
- [ ] Permisos de usuario (quién puede aprobar)

---

## 📝 Notas del Desarrollador

### Archivos Modificados:
- `app/shared/models.py` - Modelo Requisition
- `app/modules/orden_compra/routes.py` - Endpoints de recálculo y aprobación
- `app/modules/fumigacion/services/requisition_service.py` - Lógica de recálculo
- `app/templates/orden_compra/index_new.html` - UI completa
- `migrate_db.py` - Script de migración

### Estado: ✅ IMPLEMENTADO Y PROBADO

### Fecha: 2024-01-XX

### Desarrollador: GitHub Copilot con Claude Sonnet 4.5
