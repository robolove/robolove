CREATE TABLE users (
	uname VARCHAR(255) NOT NULL,
	passwd TEXT NOT NULL,
	name TEXT,
	discord TEXT,
	descr TEXT,
	warn TEXT,
	male BOOLEAN,
	pref INTEGER,
	location TEXT,
	PRIMARY KEY(uname)
);

CREATE TABLE pics (
	id INT NOT NULL AUTO_INCREMENT,
	uname VARCHAR(255),
	content VARCHAR(2097152),
	PRIMARY KEY(id),
	FOREIGN KEY(uname) REFERENCES users (uname)
);

CREATE TABLE matches (
	id INT NOT NULL AUTO_INCREMENT,
	name1 VARCHAR(255) NOT NULL,
	name2 VARCHAR(255) NOT NULL,
	hidden BOOLEAN NOT NULL DEFAULT 0,
	PRIMARY KEY(id),
	UNIQUE (name1, name2),
	FOREIGN KEY(name1) REFERENCES users (uname),
	FOREIGN KEY(name2) REFERENCES users (uname)
);

CREATE TABLE reports (
	id INT NOT NULL AUTO_INCREMENT,
	reporter VARCHAR(255) NOT NULL,
	reportee VARCHAR(255) NOT NULL,
	reason TEXT NOT NULL,
	PRIMARY KEY(id),
	FOREIGN KEY(reporter) REFERENCES users (uname),
	FOREIGN KEY(reportee) REFERENCES users (uname)
);

CREATE TABLE posts (
    id INT NOT NULL AUTO_INCREMENT,
    thread INT NOT NULL,
    poster VARCHAR(255) NOT NULL,
    content MEDIUMTEXT,
    title TEXT,
    PRIMARY KEY(id),
    FOREIGN KEY(poster) REFERENCES users (uname)
);
