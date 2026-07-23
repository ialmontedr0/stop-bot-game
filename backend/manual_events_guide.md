# Guía para Crear 10 Eventos Manualmente vía Telegram

Todos los eventos se crean desde el **chat privado con el bot** usando el comando `/newevent`.
El FSM (Formulario) guía paso a paso. Aquí están los valores para cada paso.

---

## Requisitos previos

- El bot debe estar agregado al grupo
- Vos debés ser **admin del grupo**
- Iniciar chat privado con el bot y enviar `/newevent`

---

## Flujo general de `/newevent`

Cada vez que creás un evento, el bot te va preguntando paso a paso:

| Paso | Lo que pregunta | Cómo responder |
|------|----------------|----------------|
| 0 | Seleccionar grupo | Tocás el botón del grupo |
| 1 | Tipo de evento | One-time / Diario Recurrente / Permanente |
| 2 | Nombre | Texto libre |
| 3 | Descripción | Texto libre (o poné "—" para saltar) |
| 4 | Multiplicador | Elegís valor (1.0, 1.5, 2.0, 3.0, 5.0) |
| 5a | Duración (one-time) | Fecha de inicio y fin |
| 5b | Horario (diario) | Hora inicio, hora fin, días de la semana |
| 6 | Categorías activas | Habilitar/Deshabilitar categorías |
| 6c | Multiplicadores por cat. | OFF / 1.5× / 2× / 3× / 5× por categoría |
| 7 | Tiempo y letra | Tiempo por ronda, letra forzada |
| 7d | Letras excluidas + secuencia | Toggle A-Z+Ñ, texto para secuencia |
| 8 | Bonificaciones | Velocidad, racha, penalidades, etc. |
| 8b | Modo de juego | Sudden death, wager, collaborative, etc. |
| 9 | Confirmar | Confirmar o editar |

---

## Evento 1: ⚡ Fin de Semana Explosivo

**Tipo:** `Diario Recurrente`
**Multiplicador:** 2.0
**Horario:** Sábado y Domingo, todo el día (00:00-23:59)
**Reglas:** Ninguna especial

```
→ /newevent
→ Seleccionar grupo
→ Tipo: Diario Recurrente
→ Nombre: ⚡ Fin de Semana Explosivo
→ Descripción: — (saltar)
→ Multiplicador: 2.0
→ Hora inicio: 00, Hora fin: 23
→ Días: Sáb (sat), Dom (sun)
→ Categorías: todas activas
→ Multiplicadores por cat: OFF todo
→ Tiempo: 60s, Sin letra forzada
→ Letras excluidas: ninguna
→ Bonificaciones: defaults
→ Modo: defaults
→ Confirmar ✅
```

---

## Evento 2: 🔠 Sólo Nombres y Países

**Tipo:** `Permanente`
**Multiplicador:** 1.5
**Reglas:** Solo 2 categorías activas, tiempo reducido

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🔠 Sólo Nombres y Países
→ Descripción: Solo valen Nombre y País
→ Multiplicador: 1.5
→ Categorías: DESACTIVAR: Apellido, Color, Fruta, Artista, Animal, Cosa
   (solo dejar activas: Nombre, País)
→ Multiplicadores por cat: OFF todo
→ Tiempo: 30s, Sin letra forzada
→ Confirmar ✅
```

---

## Evento 3: 🎨 Colores y Frutas con Puntos Extra

**Tipo:** `Permanente`
**Multiplicador:** 1.0
**Reglas:** Solo Color y Fruta, cada una con ×3

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🎨 Colores y Frutas
→ Descripción: Color ×3, Fruta ×3
→ Multiplicador: 1.0
→ Categorías: DESACTIVAR: Nombre, Apellido, País, Artista, Animal, Cosa
   (solo dejar: Color, Fruta)
→ Paso 6c Multiplicadores:
   → Color → tocar hasta ×3
   → Fruta → tocar hasta ×3
→ Tiempo: 45s
→ Confirmar ✅
```

---

## Evento 4: ⏳ Contrareloj (Tiempo Decreciente)

**Tipo:** `Permanente`
**Multiplicador:** 1.5
**Reglas:** El tiempo se reduce 10s por ronda

```
→ /newevent
→ Tipo: Permanente
→ Nombre: ⏳ Contrareloj
→ Descripción: Cada ronda da 10s menos
→ Multiplicador: 1.5
→ Categorías: todas activas
→ Paso 7 Tiempo:
   → Tiempo base: 60s
   → Tiempo decreciente: SÍ
   → Cantidad: 10s
→ Letra forzada: No
→ Confirmar ✅
```

---

## Evento 5: 🎯 Letra Forzada "M"

**Tipo:** `Permanente`
**Multiplicador:** 2.0
**Reglas:** Todas las palabras deben empezar con M

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🎯 Letra Forzada M
→ Descripción: Todo con M
→ Multiplicador: 2.0
→ Categorías: todas activas
→ Paso 7 Tiempo: 60s
   → Letra forzada: SÍ → M
→ Confirmar ✅
```

---

## Evento 6: 🔤 Secuencia de Letras M-R-S-P

**Tipo:** `Permanente`
**Multiplicador:** 2.5
**Reglas:** Ronda 1 con M, Ronda 2 con R, Ronda 3 con S, Ronda 4 con P, se repite

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🔤 Secuencia MRSP
→ Descripción: M → R → S → P (cíclico)
→ Multiplicador: 2.5
→ Categorías: todas activas
→ Paso 7d (Letras avanzadas):
   → Secuencia de letras: M, R, S, P (escribir: MRSP)
→ Confirmar ✅
```

---

## Evento 7: 🃏 Categoría Misteriosa

**Tipo:** `Permanente`
**Multiplicador:** 2.0
**Reglas:** Una categoría oculta que se revela al final de la ronda

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🃏 Categoría Misteriosa
→ Descripción: Una categoría sorpresa por ronda
→ Multiplicador: 2.0
→ Categorías: todas activas
→ Paso 6 (Opciones de categorías):
   → Categoría misteriosa: SÍ → elegir "Artista"
→ Paso 7 Tiempo: 60s
→ Confirmar ✅
```

---

## Evento 8: 🤝 Colaborativo

**Tipo:** `Permanente`
**Multiplicador:** 1.0
**Reglas:** Todos los jugadores suman puntos juntos

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🤝 Modo Colaborativo
→ Descripción: Todos suman para un puntaje conjunto
→ Multiplicador: 1.0
→ Categorías: todas activas
→ Paso 8b (Modo de juego):
   → Colaborativo: SÍ
→ Tiempo: 60s
→ Confirmar ✅
```

---

## Evento 9: 💀 Sudden Death (Muerte Súbita)

**Tipo:** `Permanente`
**Multiplicador:** 3.0
**Reglas:** El que no completa todas las categorías en la primera ronda, queda eliminado

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 💀 Muerte Súbita
→ Descripción: El que no completa TODO en la 1ra ronda, eliminado
→ Multiplicador: 3.0
→ Categorías: todas activas
→ Paso 8b (Modo de juego):
   → Sudden death: SÍ
   → Umbral: 1 (ronda 1 = eliminatoria)
→ Tiempo: 60s
→ Confirmar ✅
```

---

## Evento 10: 🎰 Apuesta Doble

**Tipo:** `Permanente`
**Multiplicador:** 2.0
**Reglas:** Los jugadores pueden apostar hasta el 100% de sus puntos en cada ronda

```
→ /newevent
→ Tipo: Permanente
→ Nombre: 🎰 Apuesta Doble
→ Descripción: Apostá tus puntos en cada ronda
→ Multiplicador: 2.0
→ Categorías: todas activas
→ Paso 8b (Modo de juego):
   → Apuesta (wager): SÍ
   → Máx % de apuesta: 100
→ Tiempo: 60s
→ Confirmar ✅
```

---

## Comandos de gestión

| Comando | Descripción |
|---------|-------------|
| `/toggleevent` | Pausar o reanudar un evento (sin borrarlo) |
| `/deleteevent` | Desactivar o eliminar permanentemente un evento |
| `/deleteallevents` | Eliminar TODOS los eventos de un grupo |
| `/editevent` | Modificar un evento existente |
| `/events` | Ver lista de eventos activos en el grupo |

**Nota:** Los eventos `Permanente` y `Diario Recurrente` aparecen en `/stop`
como opción de modo de juego al iniciar una partida.
