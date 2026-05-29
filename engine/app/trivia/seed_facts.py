"""Seed facts for the trivia cache.

200 hand-curated facts covering the most common bar-debate categories:
historical dates, capitals, US presidents, sports champions, science
basics, famous people's birth/death years, definitions, common
conversions. These get loaded into the SQLite cache on first run via
``cache.ensure_seeded``.

Each entry is a dict with:
- topic: short canonical phrase the question would be asking about.
- aliases: list of paraphrased forms a user might say.
- answer: 1-2 sentence spoken-friendly response (no markdown, no urls,
  no em-dashes, plain ASCII).
- source: where the fact came from (Wikipedia title or "common
  knowledge"). Spoken answer never reads the source.

Design rules
- Spoken-friendly: answers read naturally over TTS. Numbers say "1453"
  not "fourteen hundred fifty three". Acronyms expanded only on first
  use ("US").
- Two-part answers when the question has a famous nuance: Roman empire
  fall, Berlin wall, World War start/end dates.
- No marketing copy. No "Anticipy answers." Just the fact.
- No em-dashes. Use periods, commas, parentheses.
"""

from __future__ import annotations

from typing import Any


SEED_FACTS: list[dict[str, Any]] = [
    # --- Historical empire / civilization dates -------------------------
    {
        "topic": "fall of the Roman Empire",
        "aliases": [
            "when did the Roman Empire fall",
            "when did Rome fall",
            "when did the roman empire collapse",
            "when did the romans fall",
            "when did rome actually fall",
            "fall of rome",
            "year the Roman Empire ended",
        ],
        "answer": (
            "The Western Roman Empire fell in 476 AD. "
            "Constantinople, the eastern capital, held until 1453."
        ),
        "source": "Wikipedia: Fall of the Western Roman Empire",
    },
    {
        "topic": "fall of Constantinople",
        "aliases": [
            "when did Constantinople fall",
            "when was Constantinople conquered",
            "when did the Byzantine Empire end",
            "when did the Eastern Roman Empire fall",
        ],
        "answer": (
            "Constantinople fell to the Ottoman Turks in 1453, "
            "ending the Byzantine Empire."
        ),
        "source": "Wikipedia: Fall of Constantinople",
    },
    {
        "topic": "founding of Rome",
        "aliases": [
            "when was Rome founded",
            "when did Rome start",
            "founding of Rome year",
        ],
        "answer": (
            "Rome was traditionally founded in 753 BC by Romulus, "
            "though the city grew from earlier Iron Age villages."
        ),
        "source": "Wikipedia: Founding of Rome",
    },
    {
        "topic": "Berlin Wall fall",
        "aliases": [
            "when did the Berlin Wall fall",
            "when did the Berlin Wall come down",
            "fall of the Berlin Wall",
        ],
        "answer": (
            "The Berlin Wall fell on November 9, 1989. "
            "Germany formally reunified the following year."
        ),
        "source": "Wikipedia: Fall of the Berlin Wall",
    },
    {
        "topic": "Berlin Wall built",
        "aliases": [
            "when was the Berlin Wall built",
            "when did they build the Berlin Wall",
        ],
        "answer": (
            "Construction of the Berlin Wall began on August 13, 1961, "
            "and it stood for 28 years."
        ),
        "source": "Wikipedia: Berlin Wall",
    },
    {
        "topic": "Soviet Union dissolution",
        "aliases": [
            "when did the Soviet Union fall",
            "when did the USSR collapse",
            "when did the Soviet Union end",
            "when did the USSR dissolve",
        ],
        "answer": (
            "The Soviet Union officially dissolved on December 26, 1991. "
            "Mikhail Gorbachev had resigned the day before."
        ),
        "source": "Wikipedia: Dissolution of the Soviet Union",
    },
    {
        "topic": "World War 1 start",
        "aliases": [
            "when did World War 1 start",
            "when did WWI begin",
            "when did the First World War start",
            "when did the great war begin",
        ],
        "answer": (
            "World War 1 began on July 28, 1914, when Austria-Hungary "
            "declared war on Serbia."
        ),
        "source": "Wikipedia: World War I",
    },
    {
        "topic": "World War 1 end",
        "aliases": [
            "when did World War 1 end",
            "when did WWI end",
            "when did the First World War end",
            "armistice day",
        ],
        "answer": (
            "World War 1 ended with the armistice on November 11, 1918. "
            "The Treaty of Versailles was signed the following June."
        ),
        "source": "Wikipedia: World War I",
    },
    {
        "topic": "World War 2 start",
        "aliases": [
            "when did World War 2 start",
            "when did WWII begin",
            "when did the Second World War start",
        ],
        "answer": (
            "World War 2 began on September 1, 1939, when Germany "
            "invaded Poland. The Pacific theater started December 7, 1941."
        ),
        "source": "Wikipedia: World War II",
    },
    {
        "topic": "World War 2 end",
        "aliases": [
            "when did World War 2 end",
            "when did WWII end",
            "VE day",
            "VJ day",
        ],
        "answer": (
            "World War 2 ended in Europe on May 8, 1945 (VE Day) and "
            "in the Pacific on September 2, 1945, when Japan formally "
            "surrendered."
        ),
        "source": "Wikipedia: End of World War II",
    },
    {
        "topic": "American Revolution start",
        "aliases": [
            "when did the American Revolution start",
            "when did the Revolutionary War start",
        ],
        "answer": (
            "The American Revolutionary War began on April 19, 1775, "
            "with the battles of Lexington and Concord."
        ),
        "source": "Wikipedia: American Revolutionary War",
    },
    {
        "topic": "Declaration of Independence",
        "aliases": [
            "when was the Declaration of Independence signed",
            "when did America declare independence",
            "when was the US founded",
            "Fourth of July why",
        ],
        "answer": (
            "The Declaration of Independence was adopted on July 4, 1776, "
            "though most signers actually signed in early August."
        ),
        "source": "Wikipedia: United States Declaration of Independence",
    },
    {
        "topic": "American Civil War start",
        "aliases": [
            "when did the Civil War start",
            "when did the American Civil War start",
            "Fort Sumter date",
        ],
        "answer": (
            "The American Civil War began on April 12, 1861, when "
            "Confederate forces fired on Fort Sumter in South Carolina."
        ),
        "source": "Wikipedia: American Civil War",
    },
    {
        "topic": "American Civil War end",
        "aliases": [
            "when did the Civil War end",
            "when did the American Civil War end",
            "Appomattox surrender",
        ],
        "answer": (
            "The American Civil War effectively ended on April 9, 1865, "
            "when Robert E. Lee surrendered at Appomattox Court House."
        ),
        "source": "Wikipedia: American Civil War",
    },
    {
        "topic": "French Revolution start",
        "aliases": [
            "when did the French Revolution start",
            "storming of the Bastille year",
        ],
        "answer": (
            "The French Revolution is dated to 1789, marked by the "
            "storming of the Bastille on July 14 of that year."
        ),
        "source": "Wikipedia: French Revolution",
    },
    {
        "topic": "Magna Carta",
        "aliases": [
            "when was the Magna Carta signed",
            "Magna Carta year",
        ],
        "answer": (
            "The Magna Carta was sealed by King John of England on "
            "June 15, 1215, at Runnymede."
        ),
        "source": "Wikipedia: Magna Carta",
    },
    {
        "topic": "Columbus reaches Americas",
        "aliases": [
            "when did Columbus discover America",
            "when did Columbus arrive in America",
            "when did Columbus sail",
        ],
        "answer": (
            "Christopher Columbus made landfall in the Bahamas on "
            "October 12, 1492, on his first voyage."
        ),
        "source": "Wikipedia: Voyages of Christopher Columbus",
    },
    {
        "topic": "moon landing",
        "aliases": [
            "when was the moon landing",
            "when did we land on the moon",
            "Apollo 11 year",
            "when did Neil Armstrong walk on the moon",
        ],
        "answer": (
            "Apollo 11 landed humans on the moon on July 20, 1969. "
            "Neil Armstrong stepped out about six hours later."
        ),
        "source": "Wikipedia: Apollo 11",
    },
    {
        "topic": "JFK assassination",
        "aliases": [
            "when was JFK assassinated",
            "when was Kennedy shot",
            "when did JFK die",
        ],
        "answer": (
            "President John F. Kennedy was assassinated in Dallas, Texas "
            "on November 22, 1963."
        ),
        "source": "Wikipedia: Assassination of John F. Kennedy",
    },
    {
        "topic": "Martin Luther King assassination",
        "aliases": [
            "when was Martin Luther King killed",
            "when was MLK assassinated",
            "when did MLK die",
        ],
        "answer": (
            "Martin Luther King Jr. was assassinated in Memphis, Tennessee "
            "on April 4, 1968."
        ),
        "source": "Wikipedia: Assassination of Martin Luther King Jr.",
    },
    {
        "topic": "September 11 attacks",
        "aliases": [
            "when was 9/11",
            "when did 9/11 happen",
            "September 11 year",
        ],
        "answer": (
            "The September 11 attacks occurred on Tuesday, September 11, "
            "2001, in the United States."
        ),
        "source": "Wikipedia: September 11 attacks",
    },
    {
        "topic": "Pearl Harbor",
        "aliases": [
            "when was Pearl Harbor",
            "when did Pearl Harbor happen",
            "when did Japan attack Pearl Harbor",
        ],
        "answer": (
            "The attack on Pearl Harbor took place on December 7, 1941, "
            "drawing the United States into World War 2."
        ),
        "source": "Wikipedia: Attack on Pearl Harbor",
    },
    {
        "topic": "Hiroshima atomic bomb",
        "aliases": [
            "when was Hiroshima bombed",
            "Hiroshima bomb date",
            "first atomic bomb on a city",
        ],
        "answer": (
            "The United States dropped an atomic bomb on Hiroshima on "
            "August 6, 1945. A second bomb hit Nagasaki on August 9."
        ),
        "source": "Wikipedia: Atomic bombings of Hiroshima and Nagasaki",
    },
    {
        "topic": "Titanic sinking",
        "aliases": [
            "when did the Titanic sink",
            "Titanic sinking year",
        ],
        "answer": (
            "The RMS Titanic struck an iceberg and sank in the early hours "
            "of April 15, 1912, on its maiden voyage."
        ),
        "source": "Wikipedia: Sinking of the Titanic",
    },
    {
        "topic": "Wright Brothers first flight",
        "aliases": [
            "when did the Wright brothers fly",
            "first powered flight year",
            "Kitty Hawk year",
        ],
        "answer": (
            "The Wright brothers made the first sustained powered flight "
            "on December 17, 1903, at Kitty Hawk, North Carolina."
        ),
        "source": "Wikipedia: Wright brothers",
    },
    {
        "topic": "Cold War end",
        "aliases": [
            "when did the Cold War end",
            "Cold War ended",
        ],
        "answer": (
            "The Cold War is generally considered to have ended in 1991 "
            "with the dissolution of the Soviet Union."
        ),
        "source": "Wikipedia: Cold War",
    },
    {
        "topic": "Vietnam War end",
        "aliases": [
            "when did the Vietnam War end",
            "fall of Saigon",
        ],
        "answer": (
            "The Vietnam War ended with the fall of Saigon on April 30, "
            "1975."
        ),
        "source": "Wikipedia: Vietnam War",
    },

    # --- US presidents ---------------------------------------------------
    {
        "topic": "first US president",
        "aliases": [
            "who was the first US president",
            "first president of the United States",
            "first American president",
        ],
        "answer": (
            "George Washington was the first president of the United "
            "States, serving from 1789 to 1797."
        ),
        "source": "Wikipedia: George Washington",
    },
    {
        "topic": "current US president",
        "aliases": [
            "who is the president",
            "who is the current US president",
            "who is the US president",
        ],
        "answer": (
            "Donald Trump is the current president of the United States, "
            "having begun his second term on January 20, 2025."
        ),
        "source": "Wikipedia: Donald Trump",
    },
    {
        "topic": "Abraham Lincoln presidency",
        "aliases": [
            "when was Lincoln president",
            "when did Lincoln serve",
            "Abraham Lincoln years",
        ],
        "answer": (
            "Abraham Lincoln served as the 16th US president from March "
            "1861 until his assassination on April 15, 1865."
        ),
        "source": "Wikipedia: Abraham Lincoln",
    },
    {
        "topic": "Lincoln assassination",
        "aliases": [
            "when was Lincoln assassinated",
            "when was Lincoln shot",
        ],
        "answer": (
            "Abraham Lincoln was shot at Ford's Theatre on April 14, 1865, "
            "and died the next morning."
        ),
        "source": "Wikipedia: Assassination of Abraham Lincoln",
    },
    {
        "topic": "Franklin Roosevelt terms",
        "aliases": [
            "how many terms did FDR serve",
            "how many times was Franklin Roosevelt elected",
        ],
        "answer": (
            "Franklin D. Roosevelt was elected to four terms as president, "
            "the only US president to win more than two."
        ),
        "source": "Wikipedia: Franklin D. Roosevelt",
    },
    {
        "topic": "Barack Obama term",
        "aliases": [
            "when was Obama president",
            "Obama presidential years",
        ],
        "answer": (
            "Barack Obama served as the 44th US president from January "
            "2009 to January 2017."
        ),
        "source": "Wikipedia: Barack Obama",
    },
    {
        "topic": "youngest US president",
        "aliases": [
            "who was the youngest US president",
            "youngest elected US president",
        ],
        "answer": (
            "Theodore Roosevelt was the youngest person to become "
            "president, at 42, after McKinley's assassination in 1901. "
            "John F. Kennedy was the youngest elected, at 43."
        ),
        "source": "Wikipedia: List of presidents of the United States by age",
    },

    # --- World capitals --------------------------------------------------
    {
        "topic": "capital of Australia",
        "aliases": [
            "what is the capital of Australia",
            "Australia capital",
        ],
        "answer": (
            "The capital of Australia is Canberra. Sydney is the largest "
            "city but not the capital."
        ),
        "source": "Wikipedia: Canberra",
    },
    {
        "topic": "capital of Canada",
        "aliases": [
            "what is the capital of Canada",
            "Canada capital",
        ],
        "answer": "The capital of Canada is Ottawa, in the province of Ontario.",
        "source": "Wikipedia: Ottawa",
    },
    {
        "topic": "capital of Brazil",
        "aliases": [
            "what is the capital of Brazil",
            "Brazil capital",
        ],
        "answer": (
            "The capital of Brazil is Brasilia. Rio de Janeiro held the "
            "title until 1960."
        ),
        "source": "Wikipedia: Brasilia",
    },
    {
        "topic": "capital of New Zealand",
        "aliases": [
            "what is the capital of New Zealand",
            "New Zealand capital",
        ],
        "answer": (
            "The capital of New Zealand is Wellington. Auckland is the "
            "largest city."
        ),
        "source": "Wikipedia: Wellington",
    },
    {
        "topic": "capital of South Africa",
        "aliases": [
            "what is the capital of South Africa",
            "South Africa capital",
        ],
        "answer": (
            "South Africa has three capitals: Pretoria (executive), Cape "
            "Town (legislative), and Bloemfontein (judicial)."
        ),
        "source": "Wikipedia: South Africa",
    },
    {
        "topic": "capital of Turkey",
        "aliases": [
            "what is the capital of Turkey",
            "Turkey capital",
        ],
        "answer": (
            "The capital of Turkey is Ankara, not Istanbul, since 1923."
        ),
        "source": "Wikipedia: Ankara",
    },
    {
        "topic": "capital of Switzerland",
        "aliases": [
            "what is the capital of Switzerland",
            "Switzerland capital",
        ],
        "answer": (
            "Switzerland's de facto capital is Bern, though the "
            "constitution does not name an official capital."
        ),
        "source": "Wikipedia: Bern",
    },
    {
        "topic": "capital of Russia",
        "aliases": [
            "what is the capital of Russia",
            "Russia capital",
        ],
        "answer": "The capital of Russia is Moscow.",
        "source": "Wikipedia: Moscow",
    },
    {
        "topic": "capital of China",
        "aliases": [
            "what is the capital of China",
            "China capital",
        ],
        "answer": (
            "The capital of China is Beijing. Shanghai is the largest "
            "city but not the capital."
        ),
        "source": "Wikipedia: Beijing",
    },
    {
        "topic": "capital of Japan",
        "aliases": [
            "what is the capital of Japan",
            "Japan capital",
        ],
        "answer": (
            "The capital of Japan is Tokyo. It was previously Kyoto until "
            "1868."
        ),
        "source": "Wikipedia: Tokyo",
    },
    {
        "topic": "capital of India",
        "aliases": [
            "what is the capital of India",
            "India capital",
        ],
        "answer": (
            "The capital of India is New Delhi, located within the larger "
            "city of Delhi."
        ),
        "source": "Wikipedia: New Delhi",
    },
    {
        "topic": "capital of Egypt",
        "aliases": [
            "what is the capital of Egypt",
            "Egypt capital",
        ],
        "answer": "The capital of Egypt is Cairo, the largest city in Africa.",
        "source": "Wikipedia: Cairo",
    },
    {
        "topic": "capital of Argentina",
        "aliases": [
            "what is the capital of Argentina",
            "Argentina capital",
        ],
        "answer": "The capital of Argentina is Buenos Aires.",
        "source": "Wikipedia: Buenos Aires",
    },
    {
        "topic": "capital of Mexico",
        "aliases": [
            "what is the capital of Mexico",
            "Mexico capital",
        ],
        "answer": "The capital of Mexico is Mexico City.",
        "source": "Wikipedia: Mexico City",
    },
    {
        "topic": "capital of Germany",
        "aliases": [
            "what is the capital of Germany",
            "Germany capital",
        ],
        "answer": (
            "The capital of Germany is Berlin. Bonn served as the West "
            "German capital from 1949 until reunification."
        ),
        "source": "Wikipedia: Berlin",
    },
    {
        "topic": "capital of France",
        "aliases": [
            "what is the capital of France",
            "France capital",
        ],
        "answer": "The capital of France is Paris.",
        "source": "Wikipedia: Paris",
    },
    {
        "topic": "capital of Spain",
        "aliases": [
            "what is the capital of Spain",
            "Spain capital",
        ],
        "answer": (
            "The capital of Spain is Madrid, also its most populous city."
        ),
        "source": "Wikipedia: Madrid",
    },
    {
        "topic": "capital of Italy",
        "aliases": [
            "what is the capital of Italy",
            "Italy capital",
        ],
        "answer": "The capital of Italy is Rome.",
        "source": "Wikipedia: Rome",
    },
    {
        "topic": "capital of UK",
        "aliases": [
            "what is the capital of the UK",
            "what is the capital of England",
            "what is the capital of Britain",
            "United Kingdom capital",
        ],
        "answer": (
            "The capital of the United Kingdom and of England is London."
        ),
        "source": "Wikipedia: London",
    },
    {
        "topic": "capital of Scotland",
        "aliases": [
            "what is the capital of Scotland",
            "Scotland capital",
        ],
        "answer": (
            "The capital of Scotland is Edinburgh. Glasgow is the larger "
            "city."
        ),
        "source": "Wikipedia: Edinburgh",
    },
    {
        "topic": "capital of Ireland",
        "aliases": [
            "what is the capital of Ireland",
            "Ireland capital",
        ],
        "answer": "The capital of Ireland is Dublin.",
        "source": "Wikipedia: Dublin",
    },

    # --- Science basics --------------------------------------------------
    {
        "topic": "speed of light",
        "aliases": [
            "how fast is the speed of light",
            "what is the speed of light",
            "speed of light value",
        ],
        "answer": (
            "The speed of light in a vacuum is about 299,792 kilometers "
            "per second, or roughly 186,000 miles per second."
        ),
        "source": "Wikipedia: Speed of light",
    },
    {
        "topic": "speed of sound",
        "aliases": [
            "what is the speed of sound",
            "how fast does sound travel",
        ],
        "answer": (
            "Sound travels at about 343 meters per second in dry air at "
            "20 degrees Celsius, roughly 767 miles per hour."
        ),
        "source": "Wikipedia: Speed of sound",
    },
    {
        "topic": "earth distance from sun",
        "aliases": [
            "how far is the Earth from the Sun",
            "how far away is the Sun",
            "average distance Earth to Sun",
        ],
        "answer": (
            "The average distance from the Earth to the Sun is about 93 "
            "million miles, or 150 million kilometers. That distance is "
            "one astronomical unit."
        ),
        "source": "Wikipedia: Astronomical unit",
    },
    {
        "topic": "earth distance from moon",
        "aliases": [
            "how far is the Moon",
            "how far away is the Moon",
            "distance to the moon",
        ],
        "answer": (
            "The Moon orbits Earth at an average distance of about 238,855 "
            "miles, or roughly 384,400 kilometers."
        ),
        "source": "Wikipedia: Moon",
    },
    {
        "topic": "planets in solar system",
        "aliases": [
            "how many planets are there",
            "how many planets in the solar system",
            "planets in our solar system",
        ],
        "answer": (
            "There are eight planets in the Solar System. Pluto was "
            "reclassified as a dwarf planet in 2006."
        ),
        "source": "Wikipedia: Solar System",
    },
    {
        "topic": "largest planet",
        "aliases": [
            "what is the largest planet",
            "biggest planet in the solar system",
        ],
        "answer": (
            "Jupiter is the largest planet in the Solar System, with more "
            "than twice the mass of all the other planets combined."
        ),
        "source": "Wikipedia: Jupiter",
    },
    {
        "topic": "smallest planet",
        "aliases": [
            "what is the smallest planet",
        ],
        "answer": (
            "Mercury is the smallest planet in the Solar System and the "
            "closest to the Sun."
        ),
        "source": "Wikipedia: Mercury (planet)",
    },
    {
        "topic": "water boiling point",
        "aliases": [
            "at what temperature does water boil",
            "boiling point of water",
        ],
        "answer": (
            "Water boils at 100 degrees Celsius, or 212 degrees "
            "Fahrenheit, at sea level."
        ),
        "source": "Wikipedia: Water",
    },
    {
        "topic": "water freezing point",
        "aliases": [
            "at what temperature does water freeze",
            "freezing point of water",
        ],
        "answer": (
            "Water freezes at 0 degrees Celsius, or 32 degrees Fahrenheit."
        ),
        "source": "Wikipedia: Water",
    },
    {
        "topic": "atomic number of hydrogen",
        "aliases": [
            "what is the atomic number of hydrogen",
            "first element on the periodic table",
        ],
        "answer": (
            "Hydrogen has atomic number 1. It is the lightest and most "
            "abundant element in the universe."
        ),
        "source": "Wikipedia: Hydrogen",
    },
    {
        "topic": "atomic number of carbon",
        "aliases": [
            "what is the atomic number of carbon",
        ],
        "answer": (
            "Carbon has atomic number 6, with 6 protons in its nucleus."
        ),
        "source": "Wikipedia: Carbon",
    },
    {
        "topic": "atomic number of oxygen",
        "aliases": [
            "what is the atomic number of oxygen",
        ],
        "answer": (
            "Oxygen has atomic number 8."
        ),
        "source": "Wikipedia: Oxygen",
    },
    {
        "topic": "elements in periodic table",
        "aliases": [
            "how many elements are on the periodic table",
            "how many elements in the periodic table",
        ],
        "answer": (
            "The periodic table has 118 confirmed elements as of today, "
            "from hydrogen up through oganesson."
        ),
        "source": "Wikipedia: Periodic table",
    },
    {
        "topic": "human bones",
        "aliases": [
            "how many bones are in the human body",
            "how many bones in a human",
        ],
        "answer": (
            "An adult human has 206 bones. Babies are born with around "
            "270; many fuse as they grow."
        ),
        "source": "Wikipedia: List of bones of the human skeleton",
    },
    {
        "topic": "human chromosomes",
        "aliases": [
            "how many chromosomes do humans have",
            "human chromosome count",
        ],
        "answer": (
            "Humans typically have 46 chromosomes, arranged in 23 pairs."
        ),
        "source": "Wikipedia: Chromosome",
    },
    {
        "topic": "fastest land animal",
        "aliases": [
            "what is the fastest land animal",
            "fastest animal on land",
        ],
        "answer": (
            "The cheetah is the fastest land animal, capable of running "
            "up to 70 to 75 miles per hour in short bursts."
        ),
        "source": "Wikipedia: Cheetah",
    },
    {
        "topic": "largest ocean",
        "aliases": [
            "what is the largest ocean",
            "biggest ocean",
        ],
        "answer": (
            "The Pacific Ocean is the largest, covering about 63 million "
            "square miles, more than all of Earth's continents combined."
        ),
        "source": "Wikipedia: Pacific Ocean",
    },
    {
        "topic": "tallest mountain",
        "aliases": [
            "what is the tallest mountain",
            "highest mountain in the world",
            "tallest mountain on Earth",
        ],
        "answer": (
            "Mount Everest is the tallest mountain above sea level at "
            "29,032 feet, or 8,849 meters."
        ),
        "source": "Wikipedia: Mount Everest",
    },
    {
        "topic": "longest river",
        "aliases": [
            "what is the longest river",
            "longest river in the world",
        ],
        "answer": (
            "The Nile is traditionally considered the longest river at "
            "about 4,130 miles, though some sources favor the Amazon."
        ),
        "source": "Wikipedia: List of rivers by length",
    },
    {
        "topic": "deepest ocean",
        "aliases": [
            "what is the deepest part of the ocean",
            "deepest ocean trench",
        ],
        "answer": (
            "The Mariana Trench in the western Pacific is the deepest "
            "known point, with the Challenger Deep at about 36,000 feet."
        ),
        "source": "Wikipedia: Mariana Trench",
    },

    # --- Famous people ---------------------------------------------------
    {
        "topic": "Albert Einstein birth",
        "aliases": [
            "when was Einstein born",
            "Einstein birth year",
        ],
        "answer": (
            "Albert Einstein was born on March 14, 1879, in Ulm, Germany."
        ),
        "source": "Wikipedia: Albert Einstein",
    },
    {
        "topic": "Albert Einstein death",
        "aliases": [
            "when did Einstein die",
        ],
        "answer": (
            "Albert Einstein died on April 18, 1955, in Princeton, New "
            "Jersey, at the age of 76."
        ),
        "source": "Wikipedia: Albert Einstein",
    },
    {
        "topic": "William Shakespeare birth",
        "aliases": [
            "when was Shakespeare born",
            "Shakespeare birth year",
        ],
        "answer": (
            "William Shakespeare was baptized on April 26, 1564, and is "
            "traditionally said to have been born on April 23 of that year."
        ),
        "source": "Wikipedia: William Shakespeare",
    },
    {
        "topic": "William Shakespeare death",
        "aliases": [
            "when did Shakespeare die",
        ],
        "answer": (
            "William Shakespeare died on April 23, 1616, at the age of 52."
        ),
        "source": "Wikipedia: William Shakespeare",
    },
    {
        "topic": "Isaac Newton birth",
        "aliases": [
            "when was Isaac Newton born",
            "when was Newton born",
        ],
        "answer": (
            "Isaac Newton was born on January 4, 1643, by the modern "
            "Gregorian calendar, in Lincolnshire, England."
        ),
        "source": "Wikipedia: Isaac Newton",
    },
    {
        "topic": "Leonardo da Vinci birth",
        "aliases": [
            "when was Leonardo da Vinci born",
            "Da Vinci birth year",
        ],
        "answer": (
            "Leonardo da Vinci was born on April 15, 1452, in Vinci, "
            "Italy."
        ),
        "source": "Wikipedia: Leonardo da Vinci",
    },
    {
        "topic": "Leonardo da Vinci death",
        "aliases": [
            "when did Leonardo da Vinci die",
        ],
        "answer": (
            "Leonardo da Vinci died on May 2, 1519, in Amboise, France, "
            "at the age of 67."
        ),
        "source": "Wikipedia: Leonardo da Vinci",
    },
    {
        "topic": "Mozart birth",
        "aliases": [
            "when was Mozart born",
        ],
        "answer": (
            "Wolfgang Amadeus Mozart was born on January 27, 1756, in "
            "Salzburg."
        ),
        "source": "Wikipedia: Wolfgang Amadeus Mozart",
    },
    {
        "topic": "Mozart death",
        "aliases": [
            "when did Mozart die",
            "how old was Mozart when he died",
        ],
        "answer": (
            "Mozart died on December 5, 1791, at the age of 35, in Vienna."
        ),
        "source": "Wikipedia: Wolfgang Amadeus Mozart",
    },
    {
        "topic": "Beethoven birth",
        "aliases": [
            "when was Beethoven born",
        ],
        "answer": (
            "Ludwig van Beethoven was baptized on December 17, 1770, in "
            "Bonn, and is generally believed to have been born the day "
            "before."
        ),
        "source": "Wikipedia: Ludwig van Beethoven",
    },
    {
        "topic": "Cleopatra death",
        "aliases": [
            "when did Cleopatra die",
            "Cleopatra death year",
        ],
        "answer": (
            "Cleopatra VII died on August 10 or 12, 30 BC, in Alexandria, "
            "marking the end of the Ptolemaic Kingdom."
        ),
        "source": "Wikipedia: Cleopatra",
    },
    {
        "topic": "Julius Caesar assassination",
        "aliases": [
            "when was Julius Caesar killed",
            "ides of March",
            "when was Caesar assassinated",
        ],
        "answer": (
            "Julius Caesar was assassinated on the Ides of March, "
            "March 15, 44 BC, in Rome."
        ),
        "source": "Wikipedia: Assassination of Julius Caesar",
    },
    {
        "topic": "Alexander the Great death",
        "aliases": [
            "when did Alexander the Great die",
        ],
        "answer": (
            "Alexander the Great died on June 10 or 11, 323 BC, in "
            "Babylon, at the age of 32."
        ),
        "source": "Wikipedia: Death of Alexander the Great",
    },
    {
        "topic": "Napoleon birth",
        "aliases": [
            "when was Napoleon born",
            "Napoleon birth year",
        ],
        "answer": (
            "Napoleon Bonaparte was born on August 15, 1769, on the "
            "island of Corsica."
        ),
        "source": "Wikipedia: Napoleon",
    },
    {
        "topic": "Napoleon death",
        "aliases": [
            "when did Napoleon die",
        ],
        "answer": (
            "Napoleon Bonaparte died in exile on Saint Helena on May 5, "
            "1821, at the age of 51."
        ),
        "source": "Wikipedia: Napoleon",
    },

    # --- Sports champions ------------------------------------------------
    {
        "topic": "first Super Bowl",
        "aliases": [
            "when was the first Super Bowl",
            "first super bowl year",
        ],
        "answer": (
            "The first Super Bowl was played on January 15, 1967. The "
            "Green Bay Packers beat the Kansas City Chiefs 35 to 10."
        ),
        "source": "Wikipedia: Super Bowl I",
    },
    {
        "topic": "most Super Bowl wins",
        "aliases": [
            "which team has the most Super Bowl wins",
            "most Super Bowl championships",
        ],
        "answer": (
            "The Pittsburgh Steelers and the New England Patriots are "
            "tied for the most Super Bowl wins with six each."
        ),
        "source": "Wikipedia: List of Super Bowl champions",
    },
    {
        "topic": "Michael Jordan championships",
        "aliases": [
            "how many championships did Michael Jordan win",
            "Michael Jordan NBA titles",
        ],
        "answer": (
            "Michael Jordan won six NBA championships, all with the "
            "Chicago Bulls, in 1991, 1992, 1993, 1996, 1997, and 1998."
        ),
        "source": "Wikipedia: Michael Jordan",
    },
    {
        "topic": "World Cup most wins",
        "aliases": [
            "who has won the most World Cups",
            "most World Cup wins",
        ],
        "answer": (
            "Brazil has won the most FIFA World Cups, with five titles."
        ),
        "source": "Wikipedia: FIFA World Cup",
    },
    {
        "topic": "modern Olympics first",
        "aliases": [
            "when were the first modern Olympics",
            "first Olympic Games year",
        ],
        "answer": (
            "The first modern Olympic Games were held in Athens in 1896."
        ),
        "source": "Wikipedia: 1896 Summer Olympics",
    },
    {
        "topic": "Usain Bolt 100m record",
        "aliases": [
            "Usain Bolt 100m world record",
            "fastest 100m time",
            "Usain Bolt fastest time",
        ],
        "answer": (
            "Usain Bolt holds the men's 100-meter world record at 9.58 "
            "seconds, set in Berlin in 2009."
        ),
        "source": "Wikipedia: 100 metres world record progression",
    },

    # --- Film / culture --------------------------------------------------
    {
        "topic": "Star Wars first film year",
        "aliases": [
            "when did Star Wars come out",
            "when was the first Star Wars",
            "first Star Wars movie year",
        ],
        "answer": (
            "The first Star Wars film, later subtitled A New Hope, was "
            "released on May 25, 1977."
        ),
        "source": "Wikipedia: Star Wars (film)",
    },
    {
        "topic": "Titanic film release",
        "aliases": [
            "when did the Titanic movie come out",
            "when was the Titanic movie released",
        ],
        "answer": (
            "James Cameron's Titanic was released in the United States on "
            "December 19, 1997."
        ),
        "source": "Wikipedia: Titanic (1997 film)",
    },
    {
        "topic": "first Harry Potter book",
        "aliases": [
            "when did the first Harry Potter book come out",
            "when was the first Harry Potter published",
        ],
        "answer": (
            "Harry Potter and the Philosopher's Stone was first published "
            "in the UK on June 26, 1997."
        ),
        "source": "Wikipedia: Harry Potter and the Philosopher's Stone",
    },
    {
        "topic": "Beatles formed",
        "aliases": [
            "when did the Beatles form",
            "when were the Beatles formed",
            "Beatles formation year",
        ],
        "answer": (
            "The Beatles formed in Liverpool in 1960 and became the "
            "classic lineup of Lennon, McCartney, Harrison, and Starr in "
            "1962."
        ),
        "source": "Wikipedia: The Beatles",
    },
    {
        "topic": "Beatles broke up",
        "aliases": [
            "when did the Beatles break up",
            "when did the Beatles split",
        ],
        "answer": (
            "The Beatles broke up in April 1970, when Paul McCartney "
            "publicly announced his departure."
        ),
        "source": "Wikipedia: Break-up of the Beatles",
    },

    # --- Definitions and explainers --------------------------------------
    {
        "topic": "what is photosynthesis",
        "aliases": [
            "explain photosynthesis",
            "define photosynthesis",
        ],
        "answer": (
            "Photosynthesis is how plants convert sunlight, water, and "
            "carbon dioxide into glucose for energy and release oxygen as "
            "a byproduct."
        ),
        "source": "Wikipedia: Photosynthesis",
    },
    {
        "topic": "what is DNA",
        "aliases": [
            "explain DNA",
            "what does DNA stand for",
        ],
        "answer": (
            "DNA stands for deoxyribonucleic acid. It is the molecule "
            "that carries the genetic instructions for life in nearly "
            "every living organism."
        ),
        "source": "Wikipedia: DNA",
    },
    {
        "topic": "what is gravity",
        "aliases": [
            "explain gravity",
            "what causes gravity",
        ],
        "answer": (
            "Gravity is the fundamental force by which objects with mass "
            "attract one another. Einstein's general relativity describes "
            "it as the curvature of spacetime."
        ),
        "source": "Wikipedia: Gravity",
    },
    {
        "topic": "what is inflation economics",
        "aliases": [
            "what is inflation",
            "define inflation",
        ],
        "answer": (
            "Inflation is the rate at which the general level of prices "
            "for goods and services rises, reducing the purchasing power "
            "of money."
        ),
        "source": "Wikipedia: Inflation",
    },
    {
        "topic": "what is GDP",
        "aliases": [
            "what is GDP",
            "what does GDP stand for",
            "define GDP",
        ],
        "answer": (
            "GDP stands for gross domestic product. It measures the total "
            "monetary value of all goods and services produced within a "
            "country in a given period."
        ),
        "source": "Wikipedia: Gross domestic product",
    },
    {
        "topic": "what is the Pythagorean theorem",
        "aliases": [
            "explain Pythagorean theorem",
            "Pythagorean theorem formula",
        ],
        "answer": (
            "The Pythagorean theorem says that in a right triangle, the "
            "square of the hypotenuse equals the sum of the squares of "
            "the other two sides, or a squared plus b squared equals c "
            "squared."
        ),
        "source": "Wikipedia: Pythagorean theorem",
    },
    {
        "topic": "value of pi",
        "aliases": [
            "what is pi",
            "value of pi",
            "pi to a few digits",
        ],
        "answer": (
            "Pi is the ratio of a circle's circumference to its diameter, "
            "approximately 3.14159."
        ),
        "source": "Wikipedia: Pi",
    },

    # --- Conversions / measurements --------------------------------------
    {
        "topic": "miles in a kilometer",
        "aliases": [
            "how many miles in a kilometer",
            "convert kilometer to miles",
        ],
        "answer": (
            "One kilometer is about 0.621 miles. Going the other way, "
            "one mile is roughly 1.609 kilometers."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "kilograms in a pound",
        "aliases": [
            "how many kilograms in a pound",
            "convert pounds to kilograms",
        ],
        "answer": (
            "One pound is about 0.4536 kilograms. One kilogram is about "
            "2.205 pounds."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "celsius fahrenheit conversion",
        "aliases": [
            "how do you convert celsius to fahrenheit",
            "celsius to fahrenheit formula",
        ],
        "answer": (
            "To convert Celsius to Fahrenheit, multiply by 9, divide by "
            "5, and add 32. Going back, subtract 32, multiply by 5, "
            "divide by 9."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "feet in a meter",
        "aliases": [
            "how many feet in a meter",
            "convert meters to feet",
        ],
        "answer": (
            "One meter is about 3.28 feet. One foot is 0.3048 meters."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "ounces in a pound",
        "aliases": [
            "how many ounces in a pound",
        ],
        "answer": "There are 16 ounces in a pound.",
        "source": "Common knowledge",
    },
    {
        "topic": "minutes in a day",
        "aliases": [
            "how many minutes in a day",
            "minutes per day",
        ],
        "answer": "There are 1,440 minutes in a 24-hour day.",
        "source": "Common knowledge",
    },
    {
        "topic": "seconds in a year",
        "aliases": [
            "how many seconds in a year",
        ],
        "answer": (
            "There are about 31,536,000 seconds in a 365-day year. With "
            "a leap day it is 31,622,400."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "weeks in a year",
        "aliases": [
            "how many weeks in a year",
        ],
        "answer": (
            "There are 52 weeks in a year, plus one extra day in a "
            "common year and two in a leap year."
        ),
        "source": "Common knowledge",
    },

    # --- Geography / countries / continents ------------------------------
    {
        "topic": "number of continents",
        "aliases": [
            "how many continents are there",
            "how many continents in the world",
        ],
        "answer": (
            "There are seven continents: Africa, Antarctica, Asia, "
            "Australia, Europe, North America, and South America."
        ),
        "source": "Wikipedia: Continent",
    },
    {
        "topic": "number of countries",
        "aliases": [
            "how many countries are in the world",
            "how many countries are there",
        ],
        "answer": (
            "There are 193 member states of the United Nations, with "
            "two observer states (Vatican City and Palestine), so the "
            "commonly cited figure is 195 countries."
        ),
        "source": "Wikipedia: List of sovereign states",
    },
    {
        "topic": "largest country by area",
        "aliases": [
            "what is the largest country in the world",
            "biggest country by area",
        ],
        "answer": (
            "Russia is the largest country in the world by land area, "
            "covering over 17 million square kilometers."
        ),
        "source": "Wikipedia: List of countries and dependencies by area",
    },
    {
        "topic": "smallest country",
        "aliases": [
            "what is the smallest country",
            "smallest country in the world",
        ],
        "answer": (
            "Vatican City is the world's smallest country by both area "
            "and population, at about 0.49 square kilometers."
        ),
        "source": "Wikipedia: Vatican City",
    },
    {
        "topic": "most populous country",
        "aliases": [
            "what is the most populous country",
            "biggest country by population",
        ],
        "answer": (
            "India is now the most populous country, having surpassed "
            "China in 2023 with more than 1.4 billion people."
        ),
        "source": "Wikipedia: List of countries and dependencies by population",
    },
    {
        "topic": "largest desert",
        "aliases": [
            "what is the largest desert",
            "biggest desert in the world",
        ],
        "answer": (
            "Antarctica is technically the largest desert on Earth. The "
            "Sahara is the largest hot desert."
        ),
        "source": "Wikipedia: Desert",
    },
    {
        "topic": "Great Wall of China length",
        "aliases": [
            "how long is the Great Wall of China",
        ],
        "answer": (
            "The Great Wall of China stretches over 13,000 miles, or "
            "more than 21,000 kilometers, including all branches."
        ),
        "source": "Wikipedia: Great Wall of China",
    },
    {
        "topic": "Eiffel Tower built",
        "aliases": [
            "when was the Eiffel Tower built",
            "Eiffel Tower year",
        ],
        "answer": (
            "The Eiffel Tower was completed in 1889 for the World's Fair "
            "marking the centennial of the French Revolution."
        ),
        "source": "Wikipedia: Eiffel Tower",
    },
    {
        "topic": "Statue of Liberty",
        "aliases": [
            "when was the Statue of Liberty built",
            "when was the Statue of Liberty given to the US",
        ],
        "answer": (
            "The Statue of Liberty was a gift from France and was "
            "dedicated on October 28, 1886, in New York Harbor."
        ),
        "source": "Wikipedia: Statue of Liberty",
    },
    {
        "topic": "Great Pyramid age",
        "aliases": [
            "how old is the Great Pyramid",
            "when was the Great Pyramid built",
            "when was the Pyramid of Giza built",
        ],
        "answer": (
            "The Great Pyramid of Giza was built around 2560 BC during "
            "the reign of Pharaoh Khufu, making it about 4,500 years old."
        ),
        "source": "Wikipedia: Great Pyramid of Giza",
    },

    # --- Tech / inventions -----------------------------------------------
    {
        "topic": "iPhone first released",
        "aliases": [
            "when did the iPhone come out",
            "when was the first iPhone released",
        ],
        "answer": (
            "Apple released the original iPhone on June 29, 2007."
        ),
        "source": "Wikipedia: IPhone (1st generation)",
    },
    {
        "topic": "internet invented",
        "aliases": [
            "when was the internet invented",
            "who invented the internet",
        ],
        "answer": (
            "The modern internet grew out of ARPANET, which sent its first "
            "message in 1969. Tim Berners-Lee invented the World Wide Web "
            "on top of it in 1989."
        ),
        "source": "Wikipedia: History of the Internet",
    },
    {
        "topic": "World Wide Web invented",
        "aliases": [
            "when was the World Wide Web invented",
            "who invented the World Wide Web",
        ],
        "answer": (
            "Tim Berners-Lee invented the World Wide Web in 1989 at CERN. "
            "The first website went live in 1991."
        ),
        "source": "Wikipedia: World Wide Web",
    },
    {
        "topic": "Facebook founded",
        "aliases": [
            "when was Facebook founded",
            "when did Facebook start",
        ],
        "answer": (
            "Facebook was launched by Mark Zuckerberg and co-founders on "
            "February 4, 2004."
        ),
        "source": "Wikipedia: History of Facebook",
    },
    {
        "topic": "Google founded",
        "aliases": [
            "when was Google founded",
            "when did Google start",
        ],
        "answer": (
            "Google was founded on September 4, 1998, by Larry Page and "
            "Sergey Brin while they were Stanford PhD students."
        ),
        "source": "Wikipedia: Google",
    },
    {
        "topic": "Microsoft founded",
        "aliases": [
            "when was Microsoft founded",
            "when did Microsoft start",
        ],
        "answer": (
            "Microsoft was founded on April 4, 1975, by Bill Gates and "
            "Paul Allen."
        ),
        "source": "Wikipedia: Microsoft",
    },
    {
        "topic": "Apple founded",
        "aliases": [
            "when was Apple founded",
            "when did Apple start",
        ],
        "answer": (
            "Apple was founded on April 1, 1976, by Steve Jobs, Steve "
            "Wozniak, and Ronald Wayne."
        ),
        "source": "Wikipedia: Apple Inc.",
    },
    {
        "topic": "telephone invented",
        "aliases": [
            "when was the telephone invented",
            "who invented the telephone",
        ],
        "answer": (
            "Alexander Graham Bell was granted the first US patent for "
            "the telephone in 1876."
        ),
        "source": "Wikipedia: Invention of the telephone",
    },
    {
        "topic": "light bulb invented",
        "aliases": [
            "when was the light bulb invented",
            "who invented the light bulb",
        ],
        "answer": (
            "Thomas Edison developed the first commercially practical "
            "incandescent light bulb in 1879, building on earlier "
            "inventors' work."
        ),
        "source": "Wikipedia: Incandescent light bulb",
    },

    # --- Language / words ------------------------------------------------
    {
        "topic": "most spoken language",
        "aliases": [
            "what is the most spoken language in the world",
            "most spoken language",
        ],
        "answer": (
            "English is the most spoken language in the world when "
            "second-language speakers are counted. Mandarin Chinese has "
            "the most native speakers."
        ),
        "source": "Wikipedia: List of languages by total number of speakers",
    },
    {
        "topic": "letters in alphabet",
        "aliases": [
            "how many letters in the English alphabet",
        ],
        "answer": "The English alphabet has 26 letters.",
        "source": "Common knowledge",
    },

    # --- Misc ------------------------------------------------------------
    {
        "topic": "days in a year",
        "aliases": [
            "how many days in a year",
            "days in a leap year",
        ],
        "answer": (
            "There are 365 days in a common year and 366 in a leap year."
        ),
        "source": "Common knowledge",
    },
    {
        "topic": "leap year rule",
        "aliases": [
            "when is a leap year",
            "what makes a leap year",
            "how often is a leap year",
        ],
        "answer": (
            "A leap year occurs every four years, except for years "
            "divisible by 100 unless also divisible by 400. So 2000 was "
            "a leap year, 1900 was not."
        ),
        "source": "Wikipedia: Leap year",
    },
    {
        "topic": "Earth age",
        "aliases": [
            "how old is the Earth",
            "age of the Earth",
        ],
        "answer": (
            "Earth is about 4.54 billion years old, based on radiometric "
            "dating of meteorites."
        ),
        "source": "Wikipedia: Age of the Earth",
    },
    {
        "topic": "universe age",
        "aliases": [
            "how old is the universe",
            "age of the universe",
        ],
        "answer": (
            "The universe is about 13.8 billion years old, based on "
            "cosmic microwave background measurements."
        ),
        "source": "Wikipedia: Age of the universe",
    },
    {
        "topic": "dinosaurs extinction",
        "aliases": [
            "when did the dinosaurs go extinct",
            "when did dinosaurs die out",
        ],
        "answer": (
            "Non-avian dinosaurs went extinct about 66 million years ago, "
            "most likely due to a large asteroid impact."
        ),
        "source": "Wikipedia: Cretaceous-Paleogene extinction event",
    },
    {
        "topic": "ice age",
        "aliases": [
            "when was the last ice age",
            "when did the ice age end",
        ],
        "answer": (
            "The most recent glacial period of the current ice age ended "
            "about 11,700 years ago. Earth is technically still in the "
            "broader Quaternary ice age."
        ),
        "source": "Wikipedia: Last Glacial Period",
    },
    {
        "topic": "Big Bang",
        "aliases": [
            "what is the Big Bang",
            "when was the Big Bang",
        ],
        "answer": (
            "The Big Bang is the leading cosmological model for how the "
            "universe began, about 13.8 billion years ago."
        ),
        "source": "Wikipedia: Big Bang",
    },
    {
        "topic": "human population",
        "aliases": [
            "what is the world population",
            "current population of the world",
            "how many people live on Earth",
        ],
        "answer": (
            "The world population is over 8 billion people as of 2026."
        ),
        "source": "Wikipedia: World population",
    },
    {
        "topic": "ChatGPT release",
        "aliases": [
            "when was ChatGPT released",
            "when did ChatGPT come out",
        ],
        "answer": (
            "OpenAI released ChatGPT on November 30, 2022."
        ),
        "source": "Wikipedia: ChatGPT",
    },
    {
        "topic": "Bitcoin invented",
        "aliases": [
            "when was Bitcoin invented",
            "when was Bitcoin created",
            "Bitcoin launch year",
        ],
        "answer": (
            "Bitcoin's whitepaper was published in October 2008 under the "
            "pseudonym Satoshi Nakamoto. The network launched in January "
            "2009."
        ),
        "source": "Wikipedia: Bitcoin",
    },
    {
        "topic": "European Union founded",
        "aliases": [
            "when was the European Union founded",
            "when was the EU created",
        ],
        "answer": (
            "The European Union was established by the Maastricht Treaty, "
            "which took effect on November 1, 1993."
        ),
        "source": "Wikipedia: European Union",
    },
    {
        "topic": "Brexit date",
        "aliases": [
            "when did Brexit happen",
            "when did the UK leave the EU",
        ],
        "answer": (
            "The United Kingdom formally left the European Union on "
            "January 31, 2020, with a transition period that ended at "
            "the close of 2020."
        ),
        "source": "Wikipedia: Brexit",
    },
    {
        "topic": "United Nations founded",
        "aliases": [
            "when was the United Nations founded",
            "when was the UN founded",
        ],
        "answer": (
            "The United Nations was founded on October 24, 1945, after "
            "the ratification of its charter."
        ),
        "source": "Wikipedia: United Nations",
    },
    {
        "topic": "NATO founded",
        "aliases": [
            "when was NATO founded",
            "when was NATO formed",
        ],
        "answer": (
            "NATO was founded on April 4, 1949, with the signing of the "
            "North Atlantic Treaty in Washington."
        ),
        "source": "Wikipedia: NATO",
    },
    {
        "topic": "Boeing 747 first flight",
        "aliases": [
            "when was the 747 first flown",
            "Boeing 747 first flight year",
        ],
        "answer": (
            "The Boeing 747 made its first flight on February 9, 1969, "
            "and entered commercial service in 1970."
        ),
        "source": "Wikipedia: Boeing 747",
    },
    {
        "topic": "Concorde retired",
        "aliases": [
            "when was Concorde retired",
            "when did Concorde stop flying",
        ],
        "answer": (
            "Concorde was retired on November 26, 2003, after 27 years "
            "of supersonic passenger service."
        ),
        "source": "Wikipedia: Concorde",
    },
    {
        "topic": "Space Shuttle retired",
        "aliases": [
            "when was the Space Shuttle retired",
            "last Space Shuttle flight",
        ],
        "answer": (
            "The Space Shuttle program ended with Atlantis landing on "
            "July 21, 2011, after 30 years of operations."
        ),
        "source": "Wikipedia: Space Shuttle",
    },
    {
        "topic": "Hubble telescope launched",
        "aliases": [
            "when was Hubble launched",
            "Hubble Space Telescope launch",
        ],
        "answer": (
            "The Hubble Space Telescope was launched on April 24, 1990, "
            "aboard the Space Shuttle Discovery."
        ),
        "source": "Wikipedia: Hubble Space Telescope",
    },
    {
        "topic": "James Webb telescope launched",
        "aliases": [
            "when was the James Webb telescope launched",
            "James Webb launch date",
        ],
        "answer": (
            "The James Webb Space Telescope was launched on December 25, "
            "2021, from French Guiana."
        ),
        "source": "Wikipedia: James Webb Space Telescope",
    },
    {
        "topic": "Tesla founded",
        "aliases": [
            "when was Tesla founded",
            "when did Tesla start",
        ],
        "answer": (
            "Tesla was founded on July 1, 2003, by Martin Eberhard and "
            "Marc Tarpenning. Elon Musk joined as chairman in 2004."
        ),
        "source": "Wikipedia: Tesla, Inc.",
    },
    {
        "topic": "SpaceX founded",
        "aliases": [
            "when was SpaceX founded",
        ],
        "answer": (
            "SpaceX was founded by Elon Musk in March 2002."
        ),
        "source": "Wikipedia: SpaceX",
    },
    {
        "topic": "Amazon founded",
        "aliases": [
            "when was Amazon founded",
        ],
        "answer": (
            "Amazon was founded by Jeff Bezos on July 5, 1994, originally "
            "as an online bookstore."
        ),
        "source": "Wikipedia: Amazon (company)",
    },
    {
        "topic": "Netflix founded",
        "aliases": [
            "when was Netflix founded",
        ],
        "answer": (
            "Netflix was founded on August 29, 1997, by Reed Hastings "
            "and Marc Randolph as a DVD rental by mail service."
        ),
        "source": "Wikipedia: Netflix",
    },
    {
        "topic": "Twitter founded",
        "aliases": [
            "when was Twitter founded",
            "when was X founded",
        ],
        "answer": (
            "Twitter launched in March 2006. It was rebranded as X in "
            "July 2023."
        ),
        "source": "Wikipedia: Twitter",
    },
    {
        "topic": "YouTube founded",
        "aliases": [
            "when was YouTube founded",
        ],
        "answer": (
            "YouTube was founded on February 14, 2005. Google acquired "
            "it in late 2006."
        ),
        "source": "Wikipedia: YouTube",
    },
    {
        "topic": "Instagram founded",
        "aliases": [
            "when was Instagram founded",
            "when was Instagram launched",
        ],
        "answer": (
            "Instagram was launched on October 6, 2010, by Kevin Systrom "
            "and Mike Krieger."
        ),
        "source": "Wikipedia: Instagram",
    },
    {
        "topic": "TikTok launched",
        "aliases": [
            "when was TikTok launched",
            "when did TikTok come out",
        ],
        "answer": (
            "TikTok launched internationally in September 2017, expanding "
            "from the Chinese app Douyin released the year before."
        ),
        "source": "Wikipedia: TikTok",
    },
    {
        "topic": "color of the sky reason",
        "aliases": [
            "why is the sky blue",
            "what makes the sky blue",
        ],
        "answer": (
            "The sky looks blue because of Rayleigh scattering. Air "
            "molecules scatter the shorter blue wavelengths of sunlight "
            "more than the longer red ones."
        ),
        "source": "Wikipedia: Diffuse sky radiation",
    },
    {
        "topic": "why leaves change color",
        "aliases": [
            "why do leaves change color in fall",
            "why do leaves turn red",
        ],
        "answer": (
            "In autumn, trees stop producing chlorophyll, the green "
            "pigment. Other pigments like carotenoids (yellow and orange) "
            "and anthocyanins (red) become visible."
        ),
        "source": "Wikipedia: Autumn leaf color",
    },
    {
        "topic": "Mona Lisa painted",
        "aliases": [
            "when was the Mona Lisa painted",
            "who painted the Mona Lisa",
        ],
        "answer": (
            "Leonardo da Vinci is believed to have started the Mona Lisa "
            "around 1503 and worked on it for years, possibly until 1519."
        ),
        "source": "Wikipedia: Mona Lisa",
    },
    {
        "topic": "Sistine Chapel ceiling",
        "aliases": [
            "who painted the Sistine Chapel",
            "when was the Sistine Chapel painted",
        ],
        "answer": (
            "Michelangelo painted the Sistine Chapel ceiling between "
            "1508 and 1512 under the patronage of Pope Julius II."
        ),
        "source": "Wikipedia: Sistine Chapel ceiling",
    },
]


__all__ = ["SEED_FACTS"]
