CREATE TABLE IF NOT EXISTS characters (char_name TEXT UNIQUE , char_id INT PRIMARY KEY ,
        corp_id INT, alliance_id INT, faction_id INT, kills INT,
        blops_kills INT, hic_losses INT, week_kills INT, losses INT,
        solo_ratio NUMERIC, sec_status NUMERIC, last_loss_date INT,
        last_kill_date INT, avg_attackers NUMERIC, covert_prob NUMERIC,
        normal_prob NUMERIC, last_cov_ship INT, last_norm_ship INT,
        abyssal_losses INT, last_update TEXT);

CREATE TABLE IF NOT EXISTS kills (
    killmail_id INT,
    ship_id INT,
    is_covert BOOLEAN,
    is_normal BOOLEAN,
    attackers INT,
    kill_date INT);

CREATE TABLE IF NOT EXISTS corporations (id INT PRIMARY KEY, name TEXT);

CREATE TABLE IF NOT EXISTS alliances (id INT PRIMARY KEY, name TEXT);

CREATE TABLE IF NOT EXISTS factions (id INT PRIMARY KEY, name TEXT);

CREATE TABLE IF NOT EXISTS ships (id INT PRIMARY KEY, name TEXT);


