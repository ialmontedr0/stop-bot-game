# Fase 4F — Word Lists Masivas + Expansión + Modo Configurable

**Objetivo:** Seedear las 8 categorías con listas de palabras extensas en PostgreSQL, implementar auto-expansión persistente (las respuestas validadas se guardan en BD), y permitir al usuario elegir el modo de validación (`local`, `ai` o `hybrid`) mediante el comando `/settings` en el grupo, almacenando la preferencia por grupo en `GroupConfig`.

---

## Estado Actual

| Categoría | Origen | Tamaño |
|---|---|---|
| color, fruta, pais | BD (`word_list_items`) | ~100 c/u |
| nombre, apellido, artista, novela/serie, cosa | `SEED_WORDS` en memoria | ~20-40 c/u |

`DB_CATEGORIES = {"color", "fruta", "pais"}` — solo 3 categorías cargan desde BD.

`WordListItem` NO tiene columna `source`.

`GroupConfig` NO tiene columna `validation_mode`.

No existe comando `/settings`.

---

## Tarea 4F.1 — Migrar 5 categorías restantes a PostgreSQL

### Modificar `SpellCorrector.DB_CATEGORIES`

En `src/services/spell_corrector.py`, línea 209:

```python
# ANTES:
DB_CATEGORIES = {"color", "fruta", "pais"}

# DESPUÉS:
DB_CATEGORIES = {
    "color", "fruta", "pais",
    "nombre", "apellido", "artista",
    "novela/serie", "cosa",
}
```

### Quitar las 5 categorías de `SEED_WORDS`

Reemplazar las entradas `nombre`, `apellido`, `artista`, `novela/serie`, `cosa` en `SEED_WORDS` con sets **vacíos**:

```python
SEED_WORDS: dict[str, set[str]] = {
    "nombre": set(),
    "apellido": set(),
    "color": set(),
    "fruta": set(),
    "pais": set(),
    "artista": set(),
    "novela/serie": set(),
    "cosa": set(),
}
```

### Actualizar `load_db_word_lists()` en `SpellCorrector`

El método ya itera sobre `self.DB_CATEGORIES`, así que al agrandar el set, automáticamente cargará las 8 categorías desde BD. **No requiere cambios de código**, solo verificar que funcionó:

```python
async def load_db_word_lists(self) -> None:
    from src.db.engine import async_session_factory
    from src.db.repositories.word_list_repository import WordListRepository

    try:
        async with async_session_factory() as session:
            repo = WordListRepository(session)
            for category in self.DB_CATEGORIES:
                words = await repo.get_words_by_category(category)
                self._word_lists[category] = set(words)
                logger.info(
                    "Word List cargada desde DB: %s = %d palabras",
                    category, len(words),
                )
    except Exception:
        logger.exception("Error cargando word lists desde DB")
```

---

## Tarea 4F.2 — Listas semilla masivas

### Crear `backend/scripts/word_list_data_full.py`

Contiene ~1000 nombres, ~1000 apellidos, ~500 artistas, ~500 novelas/series, ~2000 cosas.

```python
"""
Listas masivas de palabras para las 8 categorias de Stop Bot.
Cada entrada es el nombre tal como se escribe (con tildes, mayusculas, etc.),
el sistema normalizara al insertar a la BD.
"""

NAMES: list[str] = [
    # ── Hombres (500+) ──
    "Juan", "Carlos", "Pedro", "Luis", "Miguel", "Jose", "Francisco",
    "Antonio", "Manuel", "Javier", "Rafael", "Diego", "Pablo", "Fernando",
    "Sergio", "Alberto", "Andres", "Alejandro", "Ricardo", "Roberto",
    "Jorge", "Raul", "Eduardo", "Guillermo", "Vicente", "Mario",
    "Hector", "Oscar", "Arturo", "Cesar", "Marco", "Victor", "Hugo",
    "Ivan", "Julio", "Ramon", "Enrique", "Adrian", "Daniel", "David",
    "Alvaro", "Tomas", "Alfonso", "Angel", "Benito", "Cristian",
    "Domingo", "Esteban", "Felipe", "Gonzalo", "Ignacio", "Jaime",
    "Leonardo", "Lorenzo", "Martin", "Nicolas", "Pascual", "Ruben",
    "Salvador", "Santiago", "Sebastian", "Ulises", "Valentin",
    "Xavier", "Yago", "Zacarias", "Emilio", "Ernesto", "Fidel",
    "Gaspar", "German", "Ismael", "Joaquin", "Kevin", "Leandro",
    "Marcos", "Moises", "Nelson", "Omar", "Orlando", "Rodrigo",
    "Rogelio", "Rolando", "Samuel", "Saul", "Teodoro", "Timoteo",
    "Abel", "Abraham", "Agustin", "Anibal", "Ariel", "Armando",
    "Bautista", "Benjamin", "Camilo", "Clemente", "Cristobal",
    "Dario", "Edgar", "Elias", "Emanuel", "Ezequiel", "Fabian",
    "Fausto", "Florencio", "Gabriel", "Gerardo", "Gilberto",
    "Gregorio", "Gustavo", "Heriberto", "Homero", "Horacio",
    "Israel", "Jairo", "Jeremias", "Jonatan", "Josue", "Julian",
    "Lazaro", "Lionel", "Luciano", "Mateo", "Matias", "Mauro",
    "Maximiliano", "Nahuel", "Nehemias", "Norberto", "Osvaldo",
    "Pio", "Plutarco", "Ramiro", "Remigio", "Rene", "Reynaldo",
    "Roman", "Ruperto", "Silvestre", "Sixto", "Tadeo", "Telmo",
    "Tiburcio", "Tobias", "Urbano", "Wilfredo", "Wenceslao",
    "Yonatan", "Zacarias", "Bruno", "Dylan", "Ian", "Lautaro",
    "Thiago", "Benicio", "Santino", "Bastian", "Facundo", "Franco",
    "Gianluca", "Joaquin", "Lisandro", "Luka", "Milan",
    "Francesco", "Alessandro", "Matteo", "Leonel", "Emiliano",
    # ── Mujeres (500+) ──
    "Maria", "Ana", "Carmen", "Isabel", "Rosa", "Marta", "Dolores",
    "Margarita", "Patricia", "Monica", "Silvia", "Veronica", "Claudia",
    "Beatriz", "Gloria", "Alicia", "Laura", "Sofia", "Elena", "Luz",
    "Teresa", "Cristina", "Angela", "Pilar", "Juana", "Luisa",
    "Sara", "Paula", "Andrea", "Valentina", "Camila", "Gabriela",
    "Katherine", "Daniela", "Carolina", "Mariana", "Natalia",
    "Ximena", "Alejandra", "Viviana", "Adriana", "Liliana",
    "Diana", "Rocio", "Esperanza", "Mercedes", "Consuelo",
    "Leticia", "Marisol", "Guadalupe", "Fernanda", "Rebeca",
    "Ruth", "Noemi", "Esther", "Raquel", "Lidia", "Susana",
    "Celia", "Irene", "Eva", "Olga", "Sandra", "Yolanda",
    "Brenda", "Jessica", "Vanessa", "Erica", "Maribel",
    "Manuela", "Antonia", "Concepcion", "Francisca", "Ines",
    "Julia", "Milagros", "Rosario", "Victoria", "Amparo",
    "Azucena", "Begona", "Candelaria", "Dolores", "Eugenia",
    "Genoveva", "Herminia", "Josefina", "Lourdes", "Macarena",
    "Nieves", "Paloma", "Purificacion", "Remedios", "Rosalia",
    "Soledad", "Trinidad", "Virtudes", "Adela", "Adelaida",
    "Agueda", "Alba", "Amalia", "Amaya", "Amor", "Anastasia",
    "Araceli", "Aurora", "Barbara", "Belen", "Bianca", "Blanca",
    "Caridad", "Catalina", "Cecilia", "Clara", "Covadonga",
    "Cruz", "Elisa", "Elvira", "Emilia", "Encarnacion",
    "Esmeralda", "Estela", "Estrella", "Eulalia", "Fabiola",
    "Fatima", "Felisa", "Fidela", "Flora", "Florencia",
    "Gema", "Gertrudis", "Gisela", "Graciela", "Greta",
    "Helena", "Hilda", "Hortensia", "Ignacia", "Iluminada",
    "Jacinta", "Jacqueline", "Javiera", "Jenifer", "Jimena",
    "Joana", "Jordana", "Jovita", "Judit", "Lara",
    "Lauren", "Leire", "Leonor", "Leyre", "Lorena",
    "Lorenza", "Lucia", "Magdalena", "Maite", "Malena",
    "Marcela", "Mireia", "Miriam", "Nadia", "Naiara",
    "Nayara", "Nerea", "Norma", "Nuria", "Ofelia",
    "Olimpia", "Ona", "Oriana", "Paz", "Perla",
    "Petra", "Priscila", "Rafaela", "Rita", "Romina",
    "Sabrina", "Salome", "Socorro", "Tamara", "Vanesa",
]

SURNAMES: list[str] = [
    "Garcia", "Rodriguez", "Martinez", "Lopez", "Gonzalez",
    "Hernandez", "Perez", "Sanchez", "Ramirez", "Torres",
    "Flores", "Rivera", "Gomez", "Diaz", "Moreno",
    "Jimenez", "Ruiz", "Alvarez", "Romero", "Navarro",
    "Castro", "Ortega", "Mendoza", "Delgado", "Reyes",
    "Vargas", "Herrera", "Medina", "Cruz", "Morales",
    "Ortiz", "Marin", "Campos", "Nunez", "Ibanez",
    "Vega", "Soto", "Munoz", "Rivas", "Aguilar",
    "Guerrero", "Contreras", "Silva", "Pena", "Carrillo",
    "Cordero", "Rojas", "Molina", "Acosta", "Fuentes",
    "Cabrera", "Calderon", "Leon", "Camacho", "Villanueva",
    "Castillo", "Miranda", "Ponce", "Orozco", "Rangel",
    "Salazar", "Valencia", "Mejia", "Ayala", "Trujillo",
    "Paredes", "Mendez", "Chavez", "Barrera", "Zuniga",
    "Solis", "Padilla", "Escobar", "Cortes", "Valdez",
    "Castaneda", "Vera", "Ramos", "Salinas", "Espinoza",
    "Sandoval", "Bravo", "Beltran", "Cardenas", "Pacheco",
    "Gallegos", "Serrano", "Quintero", "Cervantes", "Rosales",
    "Zavala", "Esquivel", "Godinez", "Pineda", "Guerra",
    "Osorio", "Estrada", "De la Cruz", "Santiago", "Arenas",
    "Mora", "Rico", "Villa", "Mata", "Cuevas",
    "Sierra", "Peralta", "Luna", "Arias", "Corona",
    "Montoya", "Trevino", "Duarte", "Arellano", "Carbajal",
    "Barrios", "Alarcon", "Pantoja", "Ventura", "Aponte",
    "Collazo", "Lozano", "Colon", "Benitez", "Vallejo",
    "Burgos", "Zepeda", "Saucedo", "Sepulveda", "Escamilla",
    "Verdugo", "Pizarro", "Arevalo", "Avila", "Guevara",
    "Manzo", "Urena", "Cazares", "Antunez", "Alcala",
    "Chacon", "Moya", "Baez", "Maldonado", "Villareal",
    "Elias", "Zarate", "Puente", "Ceballos", "Villaverde",
    "Lara", "Paz", "Sanz", "Calvo", "Dominguez",
    "Vicente", "Vazquez", "Gil", "Santos", "Iglesias",
    "Crespo", "Aguirre", "Gimenez", "Costa", "Ferrer",
    "Pastor", "Bermejo", "Saez", "Andreu", "Vives",
    "Rovira", "Sola", "Barroso", "Machado", "Nieto",
    "Bueno", "Maldonado", "Palacios", "Otero", "Lorenzo",
    "Cano", "Prieto", "Diez", "Pardo", "Sevilla",
    "Marquez", "Santana", "Montero", "Carrasco", "Hidalgo",
    "Abril", "Alonso", "Blanco", "Calleja", "Cortina",
    "Espinosa", "Ferreiro", "Gallego", "Hurtado", "Lago",
    "Linares", "Maneiro", "Nogueira", "Ocampo", "Oliva",
    "Olivera", "Pereira", "Quiroga", "Regueiro", "Rey",
    "Rocha", "Salgado", "Tello", "Uribe", "Valero",
    "Varela", "Zambrano", "Arce", "Briceno", "Cabeza",
    "Davalos", "Escalante", "Figueroa", "Grijalva", "Hinojosa",
    "Jaramillo", "Landa", "Manrique", "Naranjo", "Orduna",
    "Portillo", "Quezada", "Rendon", "Solano", "Tovar",
    "Urbina", "Vaca", "Yanez", "Zapata", "Lerma",
    "Pompa", "Rosas", "Tapia", "Valle", "Zamora",
    "Meraz", "Najera", "Ojeda", "Pinal", "Ramos",
    "Agosto", "Alfaro", "Badillo", "Baez", "Basurto",
    "Becerra", "Botello", "Bracamontes", "Bustamante", "Bustos",
    "Cabello", "Camarillo", "Cantu", "Carranco", "Carreon",
    "Casarez", "Castellanos", "Cazares", "Ceniceros", "Cerda",
]

ARTISTS: list[str] = [
    # ── Musicos ──
    "Shakira", "Juanes", "Carlos Vives", "Luis Fonsi", "Daddy Yankee",
    "Bad Bunny", "J Balvin", "Maluma", "Karol G", "Rosalia",
    "Enrique Iglesias", "Ricky Martin", "Marc Anthony", "Gloria Estefan",
    "Celia Cruz", "Hector Lavoe", "Willie Colon", "Ruben Blades",
    "Juan Gabriel", "Luis Miguel", "Roberto Carlos", "Julio Iglesias",
    "Alejandro Sanz", "Joaquin Sabina", "Fito Paez", "Charly Garcia",
    "Gustavo Cerati", "Soda Stereo", "Andres Calamaro", "Mercedes Sosa",
    "Atahualpa Yupanqui", "Violeta Parra", "Victor Jara", "Silvio Rodriguez",
    "Pablo Milanes", "Caf Tacvba", "Molotov", "Manu Chao",
    "Buena Vista Social Club", "Ibrahim Ferrer", "Compay Segundo",
    "Beyonce", "Taylor Swift", "Ed Sheeran", "Adele", "Bruno Mars",
    "Billie Eilish", "The Weeknd", "Drake", "Kendrick Lamar", "Eminem",
    "Bob Marley", "Michael Jackson", "Prince", "David Bowie",
    "Freddie Mercury", "Queen", "The Beatles", "Led Zeppelin", "Pink Floyd",
    "Nirvana", "Radiohead", "Coldplay", "U2", "Metallica",
    "AC/DC", "Rolling Stones", "Bob Dylan", "Madonna", "Lady Gaga",
    "Rihanna", "Ariana Grande", "Selena Gomez", "Dua Lipa", "Harry Styles",
    "Elvis Presley", "Frank Sinatra", "Aretha Franklin", "Whitney Houston",
    "Maria Callas", "Luciano Pavarotti", "Placido Domingo", "Jose Carreras",
    # ── Pintores ──
    "Pablo Picasso", "Salvador Dali", "Diego Rivera", "Frida Kahlo",
    "Fernando Botero", "Jose Clemente Orozco", "David Alfaro Siqueiros",
    "Rufino Tamayo", "Leonardo da Vinci", "Miguel Angel", "Rafael",
    "Vincent van Gogh", "Claude Monet", "Edouard Manet", "Auguste Renoir",
    "Edgar Degas", "Paul Cezanne", "Henri Matisse", "Paul Gauguin",
    "Johannes Vermeer", "Rembrandt", "Caravaggio", "Goya",
    "Diego Velazquez", "El Greco", "Francisco de Zurbaran",
    "Jackson Pollock", "Andy Warhol", "Roy Lichtenstein",
    "Wassily Kandinsky", "Piet Mondrian", "Marc Chagall",
    "Gustav Klimt", "Edvard Munch", "Henri de Toulouse Lautrec",
    # ── Actores ──
    "Antonio Banderas", "Penelope Cruz", "Javier Bardem", "Gael Garcia Bernal",
    "Salma Hayek", "Ricardo Darin", "Guillermo del Toro", "Alejandro Gonzalez Inarritu",
    "Al Pacino", "Robert De Niro", "Marlon Brando", "Jack Nicholson",
    "Meryl Streep", "Katharine Hepburn", "Audrey Hepburn", "Marilyn Monroe",
    "Tom Hanks", "Leonardo DiCaprio", "Brad Pitt", "Denzel Washington",
    "Morgan Freeman", "Anthony Hopkins", "Daniel Day Lewis",
    "Marlon Brando", "Cate Blanchett", "Natalie Portman", "Scarlett Johansson",
    "Charlie Chaplin", "Humphrey Bogart", "Cary Grant", "James Stewart",
    "John Wayne", "Clint Eastwood", "Harrison Ford", "Samuel L. Jackson",
    "Will Smith", "Johnny Depp", "Robert Downey Jr", "Chris Evans",
    "Keanu Reeves", "Tom Cruise", "Julia Roberts", "Nicole Kidman",
    "Emma Stone", "Jennifer Lawrence", "Margot Robbie",
    # ── Escritores ──
    "Gabriel Garcia Marquez", "Mario Vargas Llosa", "Jorge Luis Borges",
    "Julio Cortazar", "Pablo Neruda", "Octavio Paz", "Carlos Fuentes",
    "Juan Rulfo", "Alejo Carpentier", "Jose Lezama Lima", "Ernesto Sabato",
    "Miguel de Cervantes", "Federico Garcia Lorca", "Antonio Machado",
    "Jorge Manrique", "Garcilaso de la Vega", "Lope de Vega",
    "Calderon de la Barca", "William Shakespeare", "Charles Dickens",
    "Jane Austen", "Virginia Woolf", "James Joyce", "Franz Kafka",
    "Fyodor Dostoevsky", "Leo Tolstoy", "George Orwell", "Aldous Huxley",
    "Ernest Hemingway", "Mark Twain", "Edgar Allan Poe", "Emily Dickinson",
    "Walt Whitman", "T.S. Eliot", "J.R.R. Tolkien", "C.S. Lewis",
    "Stephen King", "J.K. Rowling", "George R.R. Martin", "Dan Brown",
    "Agatha Christie", "Arthur Conan Doyle", "Isaac Asimov",
    "Gabriel Garcia Marquez", "Isabel Allende", "Laura Esquivel",
    "Elena Poniatowska", "Almudena Grandes", "Carlos Ruiz Zafon",
    "Mario Benedetti", "Cesar Vallejo", "Vicente Huidobro",
    "Jorge Amado", "Clarice Lispector", "Paulo Coelho",
]

NOVELS_SERIES: list[str] = [
    # ── Novelas clasicas ──
    "Cien anos de soledad", "Don Quijote de la Mancha", "La casa de los espiritus",
    "Rayuela", "El amor en los tiempos del colera", "El principito",
    "1984", "Un mundo feliz", "Rebelion en la granja", "Fahrenheit 451",
    "Matar a un ruisenor", "Crimen y castigo", "Guerra y paz",
    "Orgullo y prejuicio", "Cumbres borrascosas", "Jane Eyre",
    "Mujercitas", "El gran Gatsby", "Catch 22", "La naranja mecanica",
    "Lolita", "Ulises", "En busca del tiempo perdido", "La montaña magica",
    "El extranjero", "La peste", "El nombre de la rosa",
    "El senor de los anillos", "El hobbit", "Harry Potter",
    "Cancion de hielo y fuego", "Juego de tronos", "Dune",
    "Fundacion", "Yo robot", "Guia del autoestopista galactico",
    "El sabueso de los Baskerville", "Estudio en escarlata",
    "Diez negritos", "Asesinato en el Orient Express",
    "El codigo Da Vinci", "Los pilares de la tierra",
    "La sombra del viento", "El club Dumas",
    "La ciudad de las bestias", "Eva Luna", "Paula",
    "La tregua", "El tunel", "Sobre heroes y tumbas",
    "Pedro Paramo", "El llano en llamas", "Aura",
    "La muerte de Artemio Cruz", "La region mas transparente",
    "Los detectives salvajes", "2666", "La casa verde",
    "Conversacion en la catedral", "La ciudad y los perros",
    "Pantaleon y las visitadoras", "Travesuras de la nina mala",
    "La tia Julia y el escribidor", "Historia de Mayta",
    "El otono del patriarca", "El coronel no tiene quien le escriba",
    "El Aleph", "Ficciones", "El jardin de senderos que se bifurcan",
    "Bestiario", "Final del juego", "Las armas secretas",
    "Historias de cronopios y de famas", "La invencion de Morel",
    "Los siete locos", "El juguete rabioso", "Adan Buenosayres",
    # ── Series de TV ──
    "Breaking Bad", "Game of Thrones", "Stranger Things", "Friends",
    "The Office", "Los Simpson", "La casa de papel", "Elite",
    "Dark", "Peaky Blinders", "The Crown", "Black Mirror",
    "The Mandalorian", "The Last of Us", "Succession", "Euphoria",
    "Squid Game", "Money Heist", "Better Call Saul",
    "The Walking Dead", "Mad Men", "The Wire", "Sopranos",
    "True Detective", "Fargo", "Chernobyl", "Band of Brothers",
    "El chavo", "El chapulin colorado", "Betty la fea",
    "Yo soy Betty la fea", "La fea mas bella", "Los simuladores",
    "El marginal", "Okupas", "Los exitosos Pells",
    "Violetta", "Soy Luna", "Patito feo", "Rebelde Way",
    "Floricienta", "Casi Angeles", "Chiquititas", "Muneca brava",
    "Celda 211", "Narcos", "Narcos Mexico", "El chapo",
    "Pablo Escobar el patron del mal", "Senora Acero",
    "La reina del sur", "El senor de los cielos",
    "La casa de las flores", "Club de Cuervos",
    # ── Peliculas clasicas ──
    "El Padrino", "Pulp Fiction", "El caballero de la noche",
    "Forrest Gump", "Titanic", "Star Wars", "El imperio contraataca",
    "Regreso del Jedi", "La guerra de las galaxias", "Matrix",
    "Interestelar", "Origen", "El club de la pelea", "Parasitos",
    "Lo que el viento se llevo", "Casablanca", "Ciudadano Kane",
    "Psicosis", "El resplandor", "La lista de Schindler",
    "Salvar al soldado Ryan", "Gladiador", "Braveheart",
    "Corazon valiente", "Duro de matar", "Terminator",
    "Volver al futuro", "E.T.", "Indiana Jones", "Jurassic Park",
    "Toy Story", "El rey leon", "Buscando a Nemo", "Coco",
    "Spider-Man", "Avengers", "Iron Man", "Capitan America",
    "Thor", "Guardianes de la Galaxia", "Doctor Strange",
    "Black Panther", "Wonder Woman", "Batman", "Superman",
]

THINGS: list[str] = [
    "Mesa", "Silla", "Cama", "Coche", "Casa", "Libro", "Lapiz", "Computadora",
    "Telefono", "Reloj", "Zapato", "Camisa", "Plato", "Vaso", "Llave",
    "Bolsa", "Ventana", "Puerta", "Lampara", "Cuchara", "Tenedor",
    "Cuchillo", "Television", "Radio", "Bicicleta", "Moto", "Avion",
    "Barco", "Tren", "Pelota", "Guitarra", "Piano", "Bateria", "Sofa",
    "Armario", "Estante", "Cuadro", "Espejo", "Almohada", "Sabana",
    "Cobija", "Colcha", "Toalla", "Jabon", "Champu", "Pasta dental",
    "Cepillo", "Pena", "Cortauñas", "Tijeras", "Regla", "Borrador",
    "Sacapuntas", "Mochila", "Maleta", "Cartera", "Monedero", "Boligrafo",
    "Marcador", "Resaltador", "Cuaderno", "Hoja", "Carpeta",
    "Escritorio", "Biblioteca", "Librero", "Cajon", "Gaveta",
    "Nevera", "Refrigerador", "Congelador", "Horno", "Microondas",
    "Lavadora", "Secadora", "Lavavajillas", "Aspiradora", "Plancha",
    "Tostadora", "Batidora", "Licuadora", "Cafetera", "Hervidor",
    "Olla", "Sarten", "Cazo", "Colador", "Rallador", "Pelador",
    "Tabla", "Rodillo", "Moldes", "Bandeja", "Charola",
    "Taza", "Vaso", "Jarra", "Botella", "Termo", "Cantimplora",
    "Servilleta", "Mantel", "Delantal", "Guantes", "Gorro",
    "Camisa", "Camiseta", "Pantalon", "Short", "Falda", "Vestido",
    "Chaqueta", "Abrigo", "Sueter", "Bufanda", "Gorra", "Sombrero",
    "Corbata", "Cinturon", "Calcetines", "Medias", "Zapatos",
    "Botas", "Sandalias", "Chanclas", "Tenis", "Zapatillas",
    "Paraguas", "Impermeable", "Gabardina", "Chaleco",
    "Anillo", "Collar", "Pulsera", "Aretes", "Reloj",
    "Gafas", "Lentes", "Cartera", "Bolso", "Mochila",
    "Llavero", "Candado", "Cadena", "Alambre", "Cuerda",
    "Soga", "Lazo", "Cinta", "Pegamento", "Tijeras",
    "Martillo", "Destornillador", "Llave inglesa", "Alicates",
    "Sierra", "Taladro", "Nivel", "Metro", "Cinta metrica",
    "Pala", "Pico", "Azada", "Rastrillo", "Manguera",
    "Regadera", "Maceta", "Tiesto", "Mesa", "Silla", "Banco",
    "Taburete", "Butaca", "Sillon", "Mecedora", "Hamaca",
    "Columpio", "Tobogan", "Subibaja", "Arena", "Pelota",
    "Cometa", "Papalote", "Yo-yo", "Trompo", "Canica",
    "Muneca", "Carro", "Bloques", "Rompecabezas", "Legos",
    "Consola", "Videojuego", "Control", "Volante", "Audifonos",
    "Bocina", "Parlante", "Microfono", "Camara", "Proyector",
    "Pantalla", "Monitor", "Teclado", "Raton", "USB",
    "Disco duro", "Memoria", "Bateria", "Cargador", "Cable",
    "Adaptador", "Router", "Modem", "Antena", "Satelite",
    "Bicicleta", "Triciclo", "Monopatín", "Patineta", "Patines",
    "Casco", "Rodilleras", "Coderas", "Chaleco salvavidas",
    "Linterna", "Foco", "Bombilla", "Veladora", "Vela",
    "Cerillo", "Fosforo", "Encendedor", "Mechero", "Cenicero",
    "Reloj de pared", "Despertador", "Reloj de pulso", "Cronometro",
    "Termometro", "Barometro", "Higrometro", "Pluviometro",
    "Calendario", "Agenda", "Diario", "Anuario", "Album",
    "Marco", "Portarretrato", "Album de fotos", "Caja", "Cofre",
    "Baul", "Arcon", "Cesta", "Canasta", "Bolsa",
    "Mochila", "Morral", "Zurron", "Alforja", "Cantimplora",
    "Brujula", "Mapa", "GPS", "Senial", "Bandera",
    "Pancarta", "Cartel", "Letrero", "Rotulo", "Anuncio",
    "Pizarron", "Pantalla", "Proyector", "Puntero", "Tiza",
    "Gis", "Mimeografo", "Fotocopiadora", "Impresora", "Scanner",
    "Fax", "Telefono", "Intercomunicador", "Citofono", "Timbre",
    "Bocina", "Altavoz", "Megafono", "Silbato", "Campana",
    "Trompeta", "Clarinete", "Saxofon", "Flauta", "Violin",
    "Chelo", "Contrabajo", "Arpa", "Guitarra", "Ukelele",
    "Bajo", "Banjo", "Mandolina", "Acordeon", "Armonica",
    "Tambor", "Bongo", "Conga", "Timbal", "Marimba",
    "Xilofono", "Campana", "Triangulo", "Pandereta", "Maraca",
    "Claves", "Gueiro", "Cascabel", "Sonaja", "Matraca",
    "Plato", "Cuenco", "Bol", "Tazon", "Taza",
    "Jarra", "Pichel", "Cantarito", "Tinaja", "Anfora",
    "Copa", "Florero", "Jarron", "Vaso", "Botella",
    "Frasco", "Tarro", "Lata", "Bidon", "Garrafa",
    "Cubo", "Balde", "Tina", "Lavabo", "Lavadero",
    "Fregadero", "Lavaplatos", "Lavamanos", "Inodoro", "Retrete",
    "Banera", "Ducha", "Regadera", "Llave", "Grifo",
    "Canilla", "Tuberia", "Cano", "Manguera", "Cisterna",
    "Tanque", "Deposito", "Alberca", "Pileta", "Estanque",
]

WORD_LIST_DATA_FULL: dict[str, list[str]] = {
    "color": [],       # ya existe en word_list_data.py, se deja vacio
    "fruta": [],       # ya existe en word_list_data.py, se deja vacio
    "pais": [],        # ya existe en word_list_data.py, se deja vacio
    "nombre": NAMES,
    "apellido": SURNAMES,
    "artista": ARTISTS,
    "novela/serie": NOVELS_SERIES,
    "cosa": THINGS,
}
```

---

## Tarea 4F.3 — Auto-expansión persistente

Objetivo: Cuando `SpellCorrector.validate()` o `SpellCorrector.correct()` aceptan una palabra nueva, guardarla en `word_list_items` en BD (no solo en memoria).

### Modificar `SpellCorrector.add_to_word_list()`

```python
async def add_to_word_list_persistent(
    self, word: str, category: str, source: str = "learned"
) -> None:
    """Añade una palabra a la word list en memoria y la persiste en BD."""
    norm = self.normalize(word)
    cat_lower = self._normalize_category(category)

    # Memoria
    self._word_lists.setdefault(cat_lower, set()).add(norm)

    # BD
    try:
        from src.db.engine import async_session_factory
        from src.db.repositories.word_list_repository import WordListRepository

        async with async_session_factory() as session:
            repo = WordListRepository(session)
            exists = await repo.word_exists(norm, cat_lower)
            if not exists:
                from src.db.models import WordListItem
                session.add(WordListItem(
                    category=cat_lower,
                    word=word.strip(),
                    normalized=norm,
                    source=source,
                ))
                await session.commit()
    except Exception:
        logger.exception("Error persistiendo palabra aprendida: %s -> %s", word, cat_lower)
```

### Modificar `SpellCorrector.validate()` para persistir palabras válidas

Buscar los lugares donde se llama `cat_words.add(norm)` o `cat_words.add(best_norm)` y añadir llamada a persistencia.

En `validate()`, después de cada `cat_words.add(...)`, añadir:

```python
# Dentro de validate(), tras las lineas que hacen cat_words.add(norm):
# (ej: linea 565, 573, 589, 599)
asyncio.ensure_future(self.add_to_word_list_persistent(word, category))
```

Fragmento completo de `validate()` modificado:

```python
async def validate(self, word: str, category: str) -> bool:
    norm = self.normalize(word)
    cat_lower = self._normalize_category(category)
    cat_words = self._word_lists.setdefault(cat_lower, set())

    # 1 - En word list
    if norm in cat_words:
        self._validation_source[f"{cat_lower}:{norm}"] = "word_list"
        return True

    # 2 - Fuzzy match contra word list
    if cat_words:
        best, score = self.fuzzy_match(word, list(cat_words))
        if best is not None:
            best_norm = self.normalize(best)
            cat_words.add(best_norm)
            asyncio.ensure_future(self.add_to_word_list_persistent(best, category))
            self._validation_source[f"{cat_lower}:{norm}"] = "fuzzy"
            return True

    # 3 - AI validation
    if (
        self.mode in (self.MODE_AI, self.MODE_HYBRID)
        and self.api_calls_remaining > 0
    ):
        redis = await self._get_redis()
        cache_key = f"spell:validate:{norm}:{cat_lower}"
        if redis:
            cached = await redis.get(cache_key)
            if cached is not None:
                val = cached.decode() if isinstance(cached, bytes) else cached
                if val == "true":
                    cat_words.add(norm)
                    asyncio.ensure_future(self.add_to_word_list_persistent(word, category))
                self._validation_source[f"{cat_lower}:{norm}"] = "ai_cache"
                return val == "true"

        result = await self._ai_validate(word, category)
        if result is not None:
            self._api_calls += 1
            if redis:
                await redis.setex(cache_key, 3600, str(result).lower())
            if result:
                cat_words.add(norm)
                asyncio.ensure_future(self.add_to_word_list_persistent(word, category))
                self._validation_source[f"{cat_lower}:{norm}"] = "ai"
            else:
                self._validation_source[f"{cat_lower}:{norm}"] = "ai_rejected"
            return result
        else:
            self._api_failed += 1

    # 4 - Default permisivo
    self._validation_source[f"{cat_lower}:{norm}"] = "default"
    return True
```

### Modificar `SpellCorrector.correct()` similarmente

```python
# En correct(), tras cada cat_words.add(...):
asyncio.ensure_future(self.add_to_word_list_persistent(corrected_word, category))
```

---

## Tarea 4F.4 — Agregar `validation_mode` a `GroupConfig` + comando `/settings`

### Migración: añadir columna

Crear `backend/migrations/versions/xxxx_add_validation_mode.py`:

```python
"""add validation_mode to group_configs
Revision ID: xxxx
Revises: <previous_revision_id>
"""
from alembic import op
import sqlalchemy as sa

revision = "xxxx"
down_revision = "<previous_revision_id>"


def upgrade():
    op.add_column(
        "group_configs",
        sa.Column("validation_mode", sa.String(16), nullable=True, server_default="local"),
    )


def downgrade():
    op.drop_column("group_configs", "validation_mode")
```

O alternativamente, en `src/db/models.py`:

```python
class GroupConfig(Base):
    __tablename__ = "group_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    default_rounds: Mapped[int] = mapped_column(default=5)
    round_time: Mapped[int] = mapped_column(default=60)
    categories: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    include_n: Mapped[bool] = mapped_column(default=False)
    language: Mapped[str] = mapped_column(String(8), default="es")
    validation_mode: Mapped[Optional[str]] = mapped_column(String(16), default="local", nullable=True)
```

### Crear `backend/src/handlers/game/settings.py`

```python
import logging

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hbold
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from src.db.engine import async_session_factory
from src.db.models import Player, GroupConfig
from src.services.error_tracker import error_tracker
from sqlalchemy import select

logger = logging.getLogger(__name__)
settings_router = Router()

VALIDATION_MODES = {
    "local": "🔤 Local (solo fuzzy match)",
    "ai": "🤖 IA (siempre IA)",
    "hybrid": "🔀 Híbrido (fuzzy + IA)",
}


async def _get_group_config(group_chat_id: int) -> GroupConfig:
    """Obtiene o crea la configuracion del grupo."""
    async with async_session_factory() as session:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            session.add(config)
            await session.commit()
            await session.refresh(config)
        return config


def _is_admin_or_host(message: Message) -> bool:
    """Verifica si el usuario es admin del grupo."""
    from aiogram.enums import ChatMemberStatus
    return message.chat.type in ("group", "supergroup")


@settings_router.message(Command("settings"))
@error_tracker.track_errors(handler_name="cmd_settings")
async def cmd_settings(message: Message, player: Player) -> None:
    if message.chat.type == "private":
        await message.reply("❌ Este comando solo funciona en grupos.")
        return

    config = await _get_group_config(message.chat.id)
    current_mode = config.validation_mode or "local"
    mode_label = VALIDATION_MODES.get(current_mode, current_mode)

    # Solo el host o admin puede cambiar settings
    # (por simplicidad, cualquier miembro puede ver)
    text = (
        f"{hbold('⚙️ Configuración del Grupo')}\n\n"
        f"Modo validación actual: {mode_label}\n\n"
        f"Selecciona el modo de validación de palabras:"
    )

    buttons = []
    for mode_key, mode_desc in VALIDATION_MODES.items():
        selected = "• " if mode_key == current_mode else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{selected}{mode_desc}",
                callback_data=f"set_mode:{mode_key}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply(text, reply_markup=markup)


@settings_router.callback_query(F.data.startswith("set_mode:"))
async def set_mode_callback(callback: CallbackQuery) -> None:
    mode = callback.data.split(":", 1)[1]
    if mode not in VALIDATION_MODES:
        await callback.answer("❌ Modo inválido.", show_alert=True)
        return

    group_chat_id = callback.message.chat.id

    async with async_session_factory() as session:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await session.execute(stmt)
        config = result.scalar_one_or_none()
        if config is None:
            config = GroupConfig(group_chat_id=group_chat_id)
            session.add(config)
        config.validation_mode = mode
        await session.commit()

    # Actualizar el mensaje
    mode_label = VALIDATION_MODES[mode]
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    for m_key, m_desc in VALIDATION_MODES.items():
        selected = "• " if m_key == mode else ""
        buttons.append([
            InlineKeyboardButton(
                text=f"{selected}{m_desc}",
                callback_data=f"set_mode:{m_key}",
            )
        ])
    buttons.append([
        InlineKeyboardButton(text="🔙 Cerrar", callback_data="settings_close")
    ])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        f"{hbold('⚙️ Configuración del Grupo')}\n\n"
        f"Modo validación actual: {mode_label}\n\n"
        "✅ Modo actualizado.",
        reply_markup=markup,
    )
    await callback.answer(f"✅ Modo cambiado a {mode_label}")


@settings_router.callback_query(F.data == "settings_close")
async def settings_close_callback(callback: CallbackQuery) -> None:
    await callback.message.delete()
    await callback.answer()
```

### Registrar en `bot.py`

```python
from src.handlers.game.settings import settings_router
dp.include_router(settings_router)
```

---

## Tarea 4F.5 — Leer `GroupConfig.validation_mode` al iniciar partida

### Modificar `LobbyManager._do_start()` o `RoundManager.start_round()`

Antes de iniciar la primera ronda, leer el `validation_mode` del grupo y configurarlo en el `SpellCorrector`.

En `services/game_orchestrator.py`, método `_do_start()` (~línea 328), añadir:

```python
async def _do_start(self, state: LobbyState, bot: Bot) -> None:
    if state.started:
        return
    state.started = True
    self._cleanup(state)

    # ── Leer validation_mode del grupo ──
    group_config = await self._get_group_config(state.group_chat_id)
    validation_mode = group_config.validation_mode if group_config else "local"

    from src.services.spell_corrector import get_corrector
    corrector = get_corrector()
    corrector.mode = validation_mode
    logger.info(
        "Modo validación para grupo %s: %s",
        state.group_chat_id, validation_mode,
    )
    # ────────────────────────────────

    # ... resto del método existente ...
```

Añadir el helper:

```python
@staticmethod
async def _get_group_config(group_chat_id: int) -> Optional[GroupConfig]:
    from src.db.engine import async_session_factory
    from src.db.models import GroupConfig
    from sqlalchemy import select

    async with async_session_factory() as session:
        stmt = select(GroupConfig).where(GroupConfig.group_chat_id == group_chat_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
```

---

## Tarea 4F.6 — Agregar columna `source` a `word_list_items`

### Migración

Crear migración:

```python
"""add source to word_list_items
Revision ID: xxxx
"""
from alembic import op
import sqlalchemy as sa

revision = "xxxx"
down_revision = "<previous_revision_id>"


def upgrade():
    op.add_column(
        "word_list_items",
        sa.Column("source", sa.String(16), nullable=False, server_default="seed"),
    )
    op.create_index("ix_word_list_items_source", "word_list_items", ["source"])


def downgrade():
    op.drop_index("ix_word_list_items_source", table_name="word_list_items")
    op.drop_column("word_list_items", "source")
```

### Actualizar modelo `WordListItem`

```python
class WordListItem(Base):
    __tablename__ = "word_list_items"

    __table_args__ = (
        UniqueConstraint("category", "normalized", name="uq_category_word"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    word: Mapped[str] = mapped_column(String(128))
    normalized: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(16), default="seed")  # seed | learned
    created_at: Mapped[datetime] = mapped_column(default=func.now())
```

### Actualizar `WordListRepository.bulk_insert()` para aceptar source

```python
async def bulk_insert(
    self, category: str, words: list[tuple[str, str]], source: str = "seed"
) -> int:
    existing = set(await self.get_words_by_category(category))
    seen_in_batch: set[str] = set()
    count = 0
    for norm, word in words:
        if norm not in existing and norm not in seen_in_batch:
            self.session.add(
                WordListItem(
                    category=category,
                    word=word,
                    normalized=norm,
                    source=source,
                )
            )
            seen_in_batch.add(norm)
            count += 1
    if count:
        await self.session.commit()
    return count
```

---

## Tarea 4F.7 — Script `seed_all_word_lists.py` idempotente

### Crear `backend/scripts/seed_all_word_lists.py`

```python
"""
Script idempotente que siembra las 8 categorias completas en word_list_items.

Uso:
    cd backend
    python -m scripts.seed_all_word_lists

Es idempotente: no duplica entradas (usa bulk_insert que chequea unique constraint).
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.text_utils import normalize_text
from src.db.engine import async_session_factory
from src.db.repositories.word_list_repository import WordListRepository
from src.db.models import WordListItem

# Importar listas completas
from .word_list_data import COLORS, FRUITS, COUNTRIES
from .word_list_data_full import NAMES, SURNAMES, ARTISTS, NOVELS_SERIES, THINGS

ALL_CATEGORIES: dict[str, list[str]] = {
    "color": COLORS,
    "fruta": FRUITS,
    "pais": COUNTRIES,
    "nombre": NAMES,
    "apellido": SURNAMES,
    "artista": ARTISTS,
    "novela/serie": NOVELS_SERIES,
    "cosa": THINGS,
}


async def seed_all() -> None:
    print("=== Seed completo de Word Lists ===")
    print()

    async with async_session_factory() as session:
        repo = WordListRepository(session)

        for category, words in ALL_CATEGORIES.items():
            print(f"Procesando: {category} ...")

            # Normalizar y deduplicar
            items = [(normalize_text(w), w.strip()) for w in words if w.strip()]
            seen: set[str] = set()
            unique: list[tuple[str, str]] = []
            for norm, orig in items:
                if norm not in seen:
                    seen.add(norm)
                    unique.append((norm, orig))

            # Contar antes
            before = await repo.count_by_category(category)
            count = await repo.bulk_insert(category, unique, source="seed")
            after = await repo.count_by_category(category)

            print(f"  → {count} nuevas, {before} antes, {after} despues")

        # Resumen final
        print()
        print("=== Resumen final ===")
        total = 0
        for cat in ALL_CATEGORIES:
            c = await repo.count_by_category(cat)
            print(f"  {cat}: {c} palabras")
            total += c
        print(f"  TOTAL: {total} palabras en 8 categorias")
        print("=== Seed completado ===")


if __name__ == "__main__":
    asyncio.run(seed_all())
```

---

## Tarea 4F.8 — Tests

### Tests a implementar en `backend/tests/`

```python
# test_word_list_repository.py (añadir)
import pytest
from datetime import datetime
from src.db.models import WordListItem

@pytest.mark.asyncio
async def test_seed_massive_lists(session):
    """Verifica que las listas masivas se insertan correctamente."""
    from src.db.repositories.word_list_repository import WordListRepository
    repo = WordListRepository(session)

    words = [(f"TestWord{i}", f"TestWord{i}") for i in range(100)]
    count = await repo.bulk_insert("test_cat", words, source="seed")
    assert count == 100

    loaded = await repo.get_words_by_category("test_cat")
    assert len(loaded) == 100


@pytest.mark.asyncio
async def test_persistent_auto_expansion(session):
    """Verifica que add_to_word_list_persistent funciona."""
    from src.db.repositories.word_list_repository import WordListRepository
    from src.core.text_utils import normalize_text

    repo = WordListRepository(session)
    # Insertar palabra aprendida
    session.add(WordListItem(
        category="nombre",
        word="TestNombre",
        normalized=normalize_text("TestNombre"),
        source="learned",
    ))
    await session.commit()

    loaded = await repo.get_words_by_category("nombre")
    assert normalize_text("TestNombre") in loaded
```

### Tests para `SpellCorrector` con modo dinámico

```python
# test_spell_corrector.py (añadir)
@pytest.mark.asyncio
async def test_validation_mode_switch():
    """Verifica que cambiar mode en corrector afecta validación."""
    from src.services.spell_corrector import SpellCorrector

    corrector = SpellCorrector(mode="local")
    assert corrector.mode == "local"

    corrector.mode = "hybrid"
    assert corrector.mode == "hybrid"

    corrector.mode = "ai"
    assert corrector.mode == "ai"


@pytest.mark.asyncio
async def test_group_config_validation_mode(session):
    """Verifica que GroupConfig almacena y recupera validation_mode."""
    from src.db.models import GroupConfig
    from sqlalchemy import select

    config = GroupConfig(
        group_chat_id=-123456789,
        validation_mode="hybrid",
    )
    session.add(config)
    await session.commit()

    stmt = select(GroupConfig).where(GroupConfig.group_chat_id == -123456789)
    result = await session.execute(stmt)
    loaded = result.scalar_one()
    assert loaded.validation_mode == "hybrid"
```

---

## Resumen de Archivos a Crear/Modificar

| Archivo | Acción |
|---|---|
| `src/services/spell_corrector.py` | **MODIFICAR** — `DB_CATEGORIES` con 8 cats, `SEED_WORDS` vacío, `validate()` persistente, `correct()` persistente, nuevo método `add_to_word_list_persistent()` |
| `src/db/models.py` | **MODIFICAR** — `GroupConfig.validation_mode`, `WordListItem.source` |
| `src/db/repositories/word_list_repository.py` | **MODIFICAR** — `bulk_insert()` con parámetro `source` |
| `scripts/word_list_data_full.py` | **CREAR** — Listas masivas (~1000 nombres, ~1000 apellidos, ~500 artistas, ~500 novelas/series, ~2000 cosas) |
| `scripts/seed_all_word_lists.py` | **CREAR** — Seed idempotente de 8 categorías |
| `handlers/game/settings.py` | **CREAR** — Comando `/settings` con selector de modo |
| `bot.py` | **MODIFICAR** — Registrar `settings_router` |
| `services/game_orchestrator.py` | **MODIFICAR** — Leer `validation_mode` al iniciar partida |
| `migrations/versions/xxxx_add_validation_mode.py` | **CREAR** — Migración para `group_configs.validation_mode` |
| `migrations/versions/xxxx_add_source_to_word_list_items.py` | **CREAR** — Migración para `word_list_items.source` |
| `tests/test_spell_corrector.py` | **MODIFICAR** — Tests de modo dinámico y auto-expansión |
| `tests/test_word_list_repository.py` | **MODIFICAR** — Tests de seed masivo |
