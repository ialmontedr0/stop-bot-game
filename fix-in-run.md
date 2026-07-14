### - Mejoras a implementar

### 1. Seed masivo de word lists (la más importante)
Ya existe el script. Solo ejecutar en Alwaysdata:
cd ~/stop-bot-game/backend
python -m scripts.seed_all_word_lists
Con ~2.000 palabras sembradas, cuando alguien escriba "Zhamira Zambrano" de nuevo:
- Primera vez: IA la rechaza → 0pts (falso negativo)
- Segunda vez: No estará en word list aún, IA igual la rechazaría
Para mitigar esto: Reescribe la lista ARTISTS en el word_list_data_full.py sin tocar los datos ya existentes en esta lista, agregando mas artistas que no esten en ella, artistas latinos importantes, leyendas ya difuntas y retiradas, artistas latinos emergentes (por ej. Zhamira Zambrano y etc), latinos de regiones, locales de paises latinos, artistas americanos, artistas internacionales europeos reconocidos y otros artistas globales muy reconocidos sin importar paises, por ejemplo: BTS, etc. agrega más artistas al archivo scripts/word_list_data_full.py en la lista ARTISTS.

### 2. Aceptar si OTRO jugador ya escribió la misma respuesta
Esta es una mejora lógica que evitaría el falso negativo de Zhamira Zambrano. En submit_answers(), antes de rechazar por IA, podrías verificar si algún otro jugador en la misma ronda ya respondió lo mismo y fue aceptado. Si hay coincidencia, no rechazar.
Pero requiere cambios en round_manager.py y acceso a respuestas de otros jugadores.

### 3. Tiempo de inicio de ronda (~4-8s)
Es la generación de imagen con Pillow. Podrías generar la imagen de fondo una sola vez al iniciar el bot y reutilizarla, solo superponiendo la letra/número. O generar la imagen en segundo plano mientras se envía el mensaje de "preparándose".

### 4. Otros artistas
Del word_list_data_full.py en la lista ARTISTS solo se quedaran artistas tal y como dice el prompt del spell_corrector: Artistas: musico, cantante o banda, actores/actrices, escritores, incluyendo famosos. Los demas como pintores se van y busca los que faltan y agregalos al listado. Debe ser una lista muy extensa, si quieres crear un archivo extra para el listado pues esta bien, deben ser artistas de cada categoria suficientes por favor.

Proporcioname toda la informacion, comandos, datos, codigo, detalles y todas las instrucciones y todo el codigo necesario para esta implementacion, no hagas ninguna implementacion ni ningun cambio tu, dame el codigo y las instrucciones a mi que yo lo hago por favor. Nota: recuerda siempre leer el phases.md y definitions.md para que te retroalimentes cuando necesites informacion de cualquier cosa. Y escribir cualquier informacion en el archivo correspondiente a la fase en desarrollo actual por ejemplo phase0-guide.md. No omitas nada, piensa en todo y selecciona las mejores opciones, arquitecturas, tecnologias, todo que me sea gratis xfa :).
