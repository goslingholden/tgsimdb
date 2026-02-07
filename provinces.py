import sqlite3

#Define connection and cursor
connection = sqlite3.connect('provinces.db')
cursor = connection.cursor()

#Create provinces table
command1 = """CREATE TABLE IF NOT EXISTS
provinces(id INTEGER PRIMARY KEY, name TEXT)"""
cursor.execute(command1)

#Add to provinces
cursor.execute("INSERT INTO provinces VALUES (1, 'Palermo')")
cursor.execute("INSERT INTO provinces VALUES (2, 'Messina')")
cursor.execute("INSERT INTO provinces VALUES (3, 'Catania')")
cursor.execute("INSERT INTO provinces VALUES (4, 'Siracusa')")

#Get results
cursor.execute("SELECT * FROM provinces")
results = cursor.fetchall()
print(results)