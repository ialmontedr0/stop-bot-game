# Alwaysdata Free-Tier Deployment

## Requisitos previos

1. Una cuenta en [Alwaysdata](https://www.alwaysdata.com) (plan gratuito).
2. Un token de bot de Telegram creado con [@BotFather](https://t.me/BotFather). Si no lo tienes:
   - Abre Telegram, busca `@BotFather` y escribe `/newbot`.
   - Sigue las instrucciones, te dará un token como `123456:ABCdef...`.
   - **Guarda ese token**, lo necesitarás en el Paso 4.

---

## Paso 1 — Crear el sitio en Alwaysdata (ya lo hiciste)

1. Ve a [admin.alwaysdata.com](https://admin.alwaysdata.com).
2. **Sites → Add a site** con estos datos:
   - **Type**: `Python`
   - **Address**: `ialmontedr0.alwaysdata.net` (sin subdominio extra)
   - **Application path**: `/home/ialmontedr0/python/stop-bot-game/backend`
   - **Working directory**: `/home/ialmontedr0/python/stop-bot-game/backend`
   - **Python version**: `3.11` (o la más reciente disponible)
   - **virtualenv directory**: `/home/ialmontedr0/python/stop-bot-game/venv`
3. Haz clic en **Save** o **Submit**.

> Los campos **Application path** y **Working directory** apuntan a la carpeta `backend/` que está dentro del repositorio `stop-bot-game`. El **virtualenv directory** es donde crearemos el entorno virtual Python adentro del mismo repositorio.

---

## Paso 2 — Crear la base de datos PostgreSQL

El plan gratuito de Alwaysdata **no** incluye una base de datos creada por defecto. Hay que crearla manualmente.

1. En el panel de Alwaysdata, ve a **SQL → PostgreSQL**.
2. Haz clic en **Add a database** (o el botón para añadir una nueva base de datos).
3. Completa los campos:
   - **Name**: `stopbot` (o el nombre que quieras)
   - **Username**: déjalo como está (tu usuario de Alwaysdata: `ialmontedr0`)
   - **Password**: escribe una contraseña segura. **Guárdala**, la necesitarás.
   - **Permissions**: `All privileges`
4. Haz clic en **Save**.

Una vez creada, verás la base de datos en una lista. La interfaz de Alwaysdata **no muestra todos los datos de conexión en la misma página**, pero los valores siguen una regla fija para tu cuenta.

Usa estos valores exactos para tu `.env`:

| Campo | Tu valor |
|---|---|
| **Host** | `postgresql-ialmontedr0.alwaysdata.net` |
| **Port** | `5432` |
| **Database name** | `stopbot` (el nombre que pusiste al crearla) |
| **Username** | `ialmontedr0` (es tu usuario de Alwaysdata) |
| **Password** | La contraseña que escribiste al crear la base de datos |

La URL de conexión se arma así:

```
DATABASE_URL=postgresql+asyncpg://USUARIO:CONTRASEÑA@HOST:PUERTO/NOMBRE_BD
```

Reemplazando con tus datos queda:

```
DATABASE_URL=postgresql+asyncpg://ialmontedr0:TU_CONTRASEÑA@postgresql-ialmontedr0.alwaysdata.net:5432/stopbot
```

> Si no recuerdas la contraseña que pusiste, ve a **SQL → PostgreSQL** en el panel, haz clic en tu base de datos y busca una opción para editar el usuario (un icono de lápiz o engranaje). Ahí puedes cambiar la contraseña por una nueva.

---

## Paso 3 — Conectarte por SSH a Alwaysdata

Alwaysdata te da acceso SSH para subir archivos y ejecutar comandos.

1. **Abre una terminal** en tu computadora:
   - **Windows**: abre PowerShell o CMD.
   - **macOS/Linux**: abre la Terminal.
2. Escribe este comando (reemplaza `ialmontedr0` por tu usuario de Alwaysdata):

```
ssh ialmontedr0@ssh-ialmontedr0.alwaysdata.net
```

3. Te pedirá tu **contraseña de Alwaysdata** (la misma del panel de control). Escríbela y presiona Enter.
4. Si es la primera vez que te conectas, te preguntará si confías en el servidor. Escribe `yes` y Enter.

> Si el comando `ssh` no existe en tu Windows, instala [OpenSSH](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse) o usa [PuTTY](https://www.putty.org/).

Cuando veas algo como `ialmontedr0@ssh:~$`, significa que **estás dentro del servidor de Alwaysdata**. Todos los comandos siguientes se ejecutan ahí.

---

## Paso 4 — Clonar el repositorio

Ya dentro del servidor Alwaysdata (SSH), crea la carpeta donde vivirá el bot:

```bash
mkdir -p ~/python && cd ~/python
```

Clona el repositorio desde GitHub:

```bash
git clone https://github.com/tuusuario/stop-bot-game.git
```

> Reemplaza `tuusuario` con tu usuario real de GitHub. Si el repositorio es privado, necesitarás configurar una [clave SSH](https://docs.github.com/en/authentication/connecting-to-github-with-ssh) o usar un token. Si es público, el comando de arriba funciona directo.

Entra a la carpeta del proyecto:

```bash
cd ~/python/stop-bot-game
```

Verifica que todo esté bien:

```bash
ls
# Deberías ver: backend/  docs/  README.md  ...
```

---

## Paso 5 — Crear el entorno virtual e instalar dependencias

Dentro de `~/python/stop-bot-game/` (todavía en SSH), ejecuta:

```bash
python3 -m venv venv
```

Esto crea una carpeta `venv/` con un Python aislado para este proyecto.

Activa el entorno virtual (cada vez que vuelvas a conectarte por SSH, tendrás que hacer esto):

```bash
source venv/bin/activate
```

Verás que el prompt cambia a `(venv) ialmontedr0@ssh:~/python/stop-bot-game$`.

Actualiza `pip`:

```bash
pip install -U pip
```

Instala las dependencias del bot:

```bash
pip install -r backend/requirements/requirements.txt
```

> Esto puede tomar 1-2 minutos. Verás muchos mensajes de instalación. Si aparece algún error con `asyncpg`, ignóralo por ahora — en Alwaysdata ya está soportado.

---

## Paso 6 — Crear el archivo .env con la configuración

Todavía en SSH, dentro de `~/python/stop-bot-game/`, crea el archivo `.env` en la carpeta `backend/`:

```bash
nano backend/.env
```

(Si `nano` no te gusta, usa `vim backend/.env` o cualquier editor).

Dentro del editor, pega esto (reemplazando con tus datos reales):

```ini
BOT_TOKEN=123456:ABCdef...token_de_botfather
DATABASE_URL=postgresql+asyncpg://ialmontedr0:tucontraseña@postgresql.alwaysdata.com:5432/ialmontedr0_stopbot
REDIS_URL=redis://localhost:6379/0
LOG_LEVEL=INFO
```

- **BOT_TOKEN**: el token que te dio @BotFather.
- **DATABASE_URL**: la URL que armaste en el Paso 2.
- **REDIS_URL**: déjalo tal cual. Como Alwaysdata no tiene Redis, el bot usará automáticamente `MemoryStorage` (guardará datos en memoria).

Para guardar y salir de `nano`:
1. Presiona `Ctrl+O` (guardar).
2. Presiona Enter (confirmar nombre de archivo).
3. Presiona `Ctrl+X` (salir).

---

## Paso 7 — Ejecutar las migraciones de la base de datos

Asegúrate de tener el entorno virtual activado (deberías ver `(venv)` al inicio del prompt):

```bash
source venv/bin/activate   # si no lo está
```

Ve a la carpeta `backend/`:

```bash
cd ~/python/stop-bot-game/backend
```

Ejecuta las migraciones con Alembic:

```bash
alembic upgrade head
```

Si todo sale bien, verás mensajes como `INFO  [alembic.runtime.migration] Running upgrade...`. No debería mostrar errores.

---

## Paso 8 — Configurar el proceso persistente en Alwaysdata

1. Vuelve al panel de Alwaysdata en tu navegador: [admin.alwaysdata.com](https://admin.alwaysdata.com).
2. Ve a **Sites** y haz clic en el sitio `ialmontedr0` (o el nombre que le pusiste).
3. Dentro de la configuración del sitio, busca la sección **Advanced** (o **Advanced configuration**).
4. En el campo **Run** (o **Command to run**), pega exactamente esto:

```
/home/ialmontedr0/python/stop-bot-game/venv/bin/python /home/ialmontedr0/python/stop-bot-game/backend/src/bot.py
```

5. **Working directory** debe decir:

```
/home/ialmontedr0/python/stop-bot-game/backend
```

6. En **Environment variables**, si no usaste el `.env` (pero sí lo creaste en el Paso 6, así que puedes dejarlo vacío). Opcionalmente puedes poner aquí las variables también.

7. Haz clic en **Save** o **Submit** en la parte inferior.

---

## Paso 9 — Verificar que el bot funciona

1. En el panel de Alwaysdata, ve a **Sites** y haz clic en tu sitio.
2. Busca la pestaña **Logs** (o **Logs / Runtime logs**).
3. Deberías ver líneas como:
   - `[BOOT] ...`
   - `Bot iniciado`
   - `Iniciando polling...`

Si ves errores, anótalos y revisa la tabla de problemas abajo.

4. Abre Telegram, busca tu bot por el nombre que le pusiste en @BotFather.
5. Envía el comando `/start`.
6. Si el bot responde, ¡está funcionando!

---

## Si algo sale mal — Problemas comunes

| Problema | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError: No module named 'asyncpg'` | Falta `libpq-dev` en Alwaysdata | Contacta al soporte de Alwaysdata pidiendo que instalen `libpq-dev`, o edita el `.env` y cambia `DATABASE_URL` a usar `sqlite+aiosqlite` (solo para pruebas): `DATABASE_URL=sqlite+aiosqlite:///./stopbot.db` |
| `BOT_TOKEN: Field required` | El archivo `.env` no se está leyendo | Conéctate por SSH y verifica que el archivo existe: `ls -la ~/python/stop-bot-game/backend/.env`. Si no existe, créalo otra vez (Paso 6). |
| `relation "player" does not exist` | No se ejecutaron las migraciones | Conéctate por SSH, activa el venv, ve a `backend/` y ejecuta `alembic upgrade head` |
| `Cannot connect to database` | La URL de PostgreSQL es incorrecta o el host no acepta conexiones | Revisa la URL en `.env`. En el panel de Alwaysdata, ve a **SQL → PostgreSQL** y asegúrate de que la IP del servidor (o 0.0.0.0) esté permitida en los ajustes de conexión. |
| El bot no responde en Telegram | El proceso no está corriendo | Ve a **Sites → Logs** y revisa si hay errores. Asegúrate de haber puesto el comando correcto en **Advanced → Run** (Paso 8). |
| `address already in use` | El health server (puerto 9090) ya está ocupado | Es normal, no afecta al bot. |

---

## Notas importantes

- **Espacio en disco**: el plan gratuito tiene 100 MB. El bot con el entorno virtual ocupa ~40 MB. Suficiente.
- **Base de datos**: PostgreSQL incluido (50 MB). Suficiente para cientos de partidas.
- **Redis**: No está disponible en el plan gratuito. No importa — el bot automáticamente usa `MemoryStorage`.
- **Reinicias el bot**: después de cambiar el `.env` o el código, ve a **Sites → Restart** en el panel de Alwaysdata. O mejor: vuelve a hacer deploy con `git pull` y reinicia el sitio.
- **Siempre activo**: mientras tengas configurado el **Run** en **Advanced**, Alwaysdata mantendrá el bot corriendo 24/7. Si el proceso muere, lo reinicia automáticamente.
