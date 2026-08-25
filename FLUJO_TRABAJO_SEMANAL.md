# 📋 Flujo de Trabajo Semanal - Sistema de Fumigación

## 🎯 Descripción General

Este documento describe el flujo completo de trabajo semanal, desde la carga del plano de cultivo hasta la generación de órdenes de fumigación, considerando el desfase temporal entre semanas de corte y aplicación.

---

## 📅 Contexto del Negocio

**Desfase Temporal:**
- Hoy es **Semana 34**
- El plano de cultivo disponible es de **Semana 33** (1 semana de retraso)
- Estamos planificando la aplicación para **Semana 35** (2 semanas adelante)

**Problema:** Al hacer la orden de compra, no tenemos las camas de 2 semanas de edad registradas en el plano, por lo que debemos **inflar camas** según presupuesto de siembra y poda.

---

## 🔄 Flujo de Trabajo Completo

### **PASO 1: Carga del Plano de Estado de Cultivo** 📥

**Ubicación:** `Catálogos y Datos > Importador Excel`

**Acciones:**
1. Seleccionar el archivo Excel con el plano de cultivo
2. **IMPORTANTE:** Especificar **¿Para qué Semana es este Plano?** (Semana de Corte)
   - Ejemplo: Si el plano es de la semana 35, ingresar `2026-35`
   - Formato: `YYYY-WW` (Año-Semana)
3. Seleccionar modo de importación:
   - **Reemplazar:** Borra todos los registros de esa semana específica y carga los nuevos
   - **Anexar:** Agrega registros nuevos sin borrar los existentes de esa semana
4. Click en **"Importar Directamente"** o **"Previsualizar y Validar"**

**Resultado:**
- ✅ Las camas se guardan con la etiqueta de semana especificada
- ✅ Evita duplicados al re-cargar el mismo plano
- ✅ Las camas estarán disponibles SOLO para rotaciones de esa semana

---

### **PASO 2: Crear Orden de Compra** 🛒

**Ubicación:** `Fumigación > Orden de Compra`

**Acciones:**
1. Seleccionar la **Semana de Planificación** (ejemplo: 2026-35)
2. **Si NO existe rotación para esa semana:**
   - Verás el mensaje: *"No existe rotación para la Semana 2026-35"*
   - Click en **"Crear Rotación para Semana 2026-35"**
3. **Si YA existe rotación:**
   - Se muestra la configuración de camas (cuántas camas están configuradas)
   - Se muestra el pedido calculado de agroquímicos

**Funcionalidad:**
- **Camas del Plano:** Carga automáticamente las camas del plano de esa semana específica
- **Bloques Ficticios:** Puedes crear bloques adicionales con camas de presupuesto
  - Útil para siembras/podas que aún no están en el plano
  - Permite comprar producto suficiente aunque las camas reales aún no existan
- **Estado de Aprobación:** 
  - PENDIENTE: Orden en revisión
  - APROBADO: Orden confirmada para compra

**Vista:**
- Tabla de configuración de camas (NO editable)
- Tabla de requisición con cantidades calculadas
- Si necesitas editar camas, el sistema te enviará a **Rotaciones Semanales**

---

### **PASO 3: Crear/Editar Rotación Semanal** 🔄

**Ubicación:** `Fumigación > Rotaciones Semanales > Nueva Rotación`

**Sub-Pasos:**

#### **3.1 - Matriz de Asignación (Drag & Drop)** 🎯
- Arrastrar productos a celdas (Cultivo × Estado Fenológico)
- Matriz muestra productos por vuelta
- **Drag & Drop activo por defecto**
- **Prevención de duplicados:** Si intentas arrastrar un producto que ya existe en la celda, verás notificación

#### **3.2 - Revisión y Calibración de Camas** 🔧
- **Camas cargadas:** Se muestran las camas del plano de la semana de esta rotación
- **SIN filtro por vuelta:** Todas las camas son universales
- **Seleccionar vueltas:** Marca los checkboxes de las vueltas donde aplicarás esta configuración
- **Ajustar camas:** Modifica bloques, sufijos, edades, camas estándar según necesidad real
- Click en **"Guardar Configuración de Camas"**

**Resultado:**
- ✅ Configuración guardada con las vueltas seleccionadas
- ✅ Solo las vueltas marcadas usarán esta configuración personalizada
- ✅ Otras vueltas usarán el cálculo automático estándar

#### **3.3 - Comparación: Pedido vs Real Ajustado** 📊
- **Pedido (Orden de Compra):** Muestra cuánto se pidió originalmente
- **Real Ajustado:** Muestra cuánto se va a usar realmente según configuración de paso 3.2
- **Aplicaciones Extras:** Muestra manchas/aplicaciones adicionales
- **Total Final:** Suma de todo lo que se va a aplicar

**Acciones:**
- Generar órdenes de fumigación por vuelta
- Aprobar rotación

---

### **PASO 4: Aplicaciones Extras / Manchas** 🎨

**Ubicación:** `Fumigación > Aplicaciones Extras / Manchas`

**Funcionalidad:**
- Igual que rotaciones, pero para aplicaciones puntuales
- Carga las camas del plano de la semana especificada
- Permite seleccionar:
  - Qué bloques/camas necesitan aplicación
  - Qué agroquímico aplicar
  - Para qué semana es la aplicación adicional

**Uso típico:**
- Manchas de plagas en bloques específicos
- Aplicaciones correctivas
- Tratamientos especiales fuera de la rotación regular

---

## 🔑 Puntos Clave

### ✅ **Ventajas del Nuevo Sistema**

1. **Identificación por Semana:**
   - Cada plano está etiquetado con su semana de corte
   - Las edades corresponden exactamente a esa semana
   - No hay confusión sobre qué camas usar

2. **Sin Duplicados:**
   - Al re-cargar el mismo plano, se eliminan registros antiguos de esa semana
   - Garantiza datos limpios y actualizados

3. **Bloques Ficticios:**
   - Permite armar orden de compra con camas proyectadas
   - Compensas el desfase del plano
   - Ajustas en rotaciones a lo real cuando ya tienes el plano actualizado

4. **Orden de Compra Mantiene Contexto:**
   - Al cambiar de semana, el sistema recuerda tu selección
   - No salta a otra semana automáticamente
   - Puedes revisar semanas sin rotación y crearlas desde ahí

5. **Vueltas Flexibles:**
   - Configuras camas una vez
   - Seleccionas a qué vueltas aplicar
   - Otras vueltas usan cálculo automático

---

## 📊 Ejemplo Práctico

**Situación:**
- Hoy: **Semana 34**
- Plano disponible: **Semana 33**
- Planificación: **Semana 35**

**Pasos:**

1. **Cargar Plano Semana 35** (si ya lo tienes):
   - Ir a Importador Excel
   - Subir archivo
   - Especificar: `2026-35`
   - Importar

2. **Si NO tienes plano de Semana 35 aún:**
   - Ir a Orden de Compra
   - Seleccionar Semana 35
   - Crear rotación
   - En paso 3.2, crear bloques ficticios con camas de presupuesto
   - Guardar configuración

3. **Cuando llegue el plano real de Semana 35:**
   - Cargar plano especificando semana 35
   - Ir a Rotaciones > Editar
   - En paso 3.2, ajustar camas a las reales del plano
   - Guardar

4. **Generar Orden:**
   - En paso 3.3, revisar comparación
   - Aprobar rotación
   - Generar órdenes de fumigación

---

## 🛠️ Solución de Problemas

### **No veo las camas esperadas en Revisión de Camas**
✅ Verifica que el plano se haya cargado con la misma semana que la rotación

### **Al cambiar semana en Orden de Compra, vuelve a otra semana**
✅ Esto ya está corregido. Ahora mantiene la semana seleccionada

### **Se duplican registros al re-cargar plano**
✅ Usa modo "Reemplazar" y especifica correctamente la semana

### **No puedo arrastrar productos en la matriz**
✅ Drag & drop está activado por defecto. Verifica que el navegador lo soporte

### **El producto se duplica al arrastrarlo**
✅ El sistema ahora previene duplicados automáticamente con notificación

---

## 📞 Soporte

Para preguntas o problemas, contacta al equipo de desarrollo.

**Versión del Sistema:** 1.0.0  
**Última Actualización:** 2026-08-19
