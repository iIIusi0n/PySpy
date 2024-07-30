import json
import logging
import threading
import time
import requests
import config
import db
import statusmsg

Logger = logging.getLogger(__name__)

def post_req_ccp(esi_path, json_data):
    url = f"https://esi.evetech.net/latest/{esi_path}?datasource=tranquility"
    try:
        r = requests.post(url, json_data)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        Logger.info(f"Error in CCP request: {e}", exc_info=True)
        statusmsg.push_status(f"CCP SERVER ERROR: {r.status_code} ({r.text})")
        return "server_error"

def get_killmail(id, hash):
    url = f"https://esi.evetech.net/latest/killmails/{id}/{hash}/?datasource=tranquility"
    headers = {
        "User-Agent": "PySpy, Forked by: Kibeom Lee, https://github.com/iIIusi0n/PySpy, Discord: ppc64_"
    }
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        Logger.info(f"Error in killmail request: {e}", exc_info=True)
        if not isinstance(e, requests.exceptions.Timeout):
            statusmsg.push_status(f"CCP SERVER ERROR: {r.status_code} ({r.text})")
        return "server_error"

def is_cyno_ship(killmail, cyno_types, cyno_item_id):
    if not isinstance(killmail, dict):
        Logger.error("No valid killmail provided.", exc_info=True)
        return False

    try:
        ship_id = killmail["victim"]["ship_type_id"]
        items = killmail["victim"]["items"]
    except KeyError:
        Logger.error("No ship_type_id found in killmail.", exc_info=True)
        return False

    if ship_id not in cyno_types:
        return False

    return any(item["item_type_id"] == cyno_item_id for item in items)

def is_cov_cyno_ship(killmail):
    return is_cyno_ship(killmail, config.COV_CYNOS, 28646)

def is_norm_cyno_ship(killmail):
    return is_cyno_ship(killmail, config.NORM_CYNOS, 21096)

def killmail_date_to_int(date):
    try:
        return int(date.split("T")[0].replace("-", ""))
    except Exception:
        Logger.error("Failed to convert date to int.", exc_info=True)
        return 0

def cache_killmail(id, hash, conn_dsk, cur_dsk):
    cur_dsk.execute(
        "SELECT ship_id, is_covert, is_normal, attackers, kill_date FROM kills WHERE killmail_id = ?",
        (id,)
    )
    result = cur_dsk.fetchone()
    if result:
        return result

    killmail = get_killmail(id, hash)
    if killmail == "server_error":
        return "network_error"

    is_cov = is_cov_cyno_ship(killmail)
    is_norm = is_norm_cyno_ship(killmail)
    ship_id = killmail["victim"]["ship_type_id"]
    attackers = len(killmail["attackers"])
    kill_date = killmail_date_to_int(killmail["killmail_time"])

    cur_dsk.execute(
        "INSERT INTO kills (killmail_id, ship_id, is_covert, is_normal, attackers, kill_date) VALUES (?, ?, ?, ?, ?, ?)",
        (id, ship_id, is_cov, is_norm, attackers, kill_date)
    )
    conn_dsk.commit()
    return ship_id, is_cov, is_norm, attackers, kill_date

def get_zkillboard_data(url, char_id):
    headers = {
        "Accept-Encoding": "gzip",
        "User-Agent": "PySpy, Forked by: Kibeom Lee, https://github.com/iIIusi0n/PySpy, Discord: ppc64_"
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        Logger.info(f"Error in zKillboard request for character ID {char_id}: {e}", exc_info=True)
        statusmsg.push_status(f"ZKILL SERVER ERROR: {r.status_code} ({r.text})")
        return None

def get_kills(char_id, conn_dsk, cur_dsk):
    last_kill_date = 0
    avg_attackers = 0

    url = f"https://zkillboard.com/api/kills/characterID/{char_id}/"
    kills_data = get_zkillboard_data(url, char_id)

    if not kills_data:
        return last_kill_date, avg_attackers

    kills_data = kills_data[:100]

    for kill in kills_data:
        kill_id = kill["killmail_id"]
        kill_hash = kill["zkb"]["hash"]
        result = cache_killmail(kill_id, kill_hash, conn_dsk, cur_dsk)
        if result == "network_error":
            return last_kill_date, avg_attackers
        ship_id, is_cov, is_norm, attackers, kill_date = result
        last_kill_date = max(last_kill_date, kill_date)
        avg_attackers += attackers

    if kills_data:
        avg_attackers /= len(kills_data)

    return last_kill_date, avg_attackers

def get_losses(char_id, conn_dsk, cur_dsk):
    last_loss_date = covert_prob = normal_prob = last_cov_ship = last_norm_ship = abyssal_losses = 0
    last_cov_date = last_norm_date = 0

    url = f"https://zkillboard.com/api/losses/characterID/{char_id}/"
    losses_data = get_zkillboard_data(url, char_id)

    if not losses_data:
        return last_loss_date, covert_prob, normal_prob, last_cov_ship, last_norm_ship, abyssal_losses

    losses_data = losses_data[:50]

    for loss in losses_data:
        loss_id = loss["killmail_id"]
        loss_hash = loss["zkb"]["hash"]
        result = cache_killmail(loss_id, loss_hash, conn_dsk, cur_dsk)
        if result == "network_error":
            return last_loss_date, covert_prob, normal_prob, last_cov_ship, last_norm_ship, abyssal_losses
        ship_id, is_cov, is_norm, attackers, loss_date = result
        last_loss_date = max(last_loss_date, loss_date)
        if is_cov:
            covert_prob += 1
            if loss_date > last_cov_date:
                last_cov_date = loss_date
                last_cov_ship = ship_id
        if is_norm:
            normal_prob += 1
            if loss_date > last_norm_date:
                last_norm_date = loss_date
                last_norm_ship = ship_id
        if "loc:abyssal" in loss["zkb"]["labels"]:
            abyssal_losses += 1

    if losses_data:
        covert_prob /= len(losses_data)
        normal_prob /= len(losses_data)

    return last_loss_date, covert_prob, normal_prob, last_cov_ship, last_norm_ship, abyssal_losses

class Query_zKill(threading.Thread):
    def __init__(self, char_id, q):
        super(Query_zKill, self).__init__()
        self.daemon = True
        self._char_id = char_id
        self._queue = q

    def run(self):
        conn, cur = db.connect_killmail_db()

        url = f"https://zkillboard.com/api/stats/characterID/{self._char_id}/"
        stats_data = get_zkillboard_data(url, self._char_id)

        if not stats_data:
            cur.close()
            conn.close()
            return

        kills = stats_data.get("shipsDestroyed", 0)
        blops_kills = stats_data.get("groups", {}).get("898", {}).get("shipsDestroyed", 0)
        hic_losses = stats_data.get("groups", {}).get("894", {}).get("shipsLost", 0)
        week_kills = stats_data.get("activepvp", {}).get("kills", {}).get("count", 0)
        losses = stats_data.get("shipsLost", 0)
        solo_ratio = int(stats_data.get("soloKills", 0)) / int(stats_data.get("shipsDestroyed", 1))
        sec_status = stats_data.get("info", {}).get("secStatus", 0)

        time.sleep(1)
        last_kill_date, avg_attackers = get_kills(self._char_id, conn, cur)

        time.sleep(1)
        last_loss_date, covert_prob, normal_prob, last_cov_ship, last_norm_ship, abyssal_losses = get_losses(self._char_id, conn, cur)

        self._queue.put([
            kills, blops_kills, hic_losses, week_kills, losses, solo_ratio,
            sec_status, last_loss_date, last_kill_date, avg_attackers,
            covert_prob, normal_prob, last_cov_ship, last_norm_ship,
            abyssal_losses, self._char_id
        ])

        cur.close()
        conn.close()

        Logger.info(f"zKillboard API query for character ID {self._char_id} completed.")

def get_ship_data():
    all_ship_ids = get_all_ship_ids()
    if not isinstance(all_ship_ids, (list, tuple)) or len(all_ship_ids) < 1:
        Logger.error("No valid ship ids provided.", exc_info=True)
        return

    url = "https://esi.evetech.net/v2/universe/names/?datasource=tranquility"
    json_data = json.dumps(all_ship_ids)
    try:
        r = requests.post(url, json_data)
        r.raise_for_status()
        return [[ship['id'], ship['name']] for ship in r.json()]
    except requests.exceptions.RequestException as e:
        Logger.error(f"Error in ship data request: {e}", exc_info=True)
        return "server_error"

def get_all_ship_ids():
    url = "https://esi.evetech.net/v1/insurance/prices/?datasource=tranquility"
    try:
        r = requests.get(url)
        r.raise_for_status()
        ship_ids = [str(ship['type_id']) for ship in r.json()]
        Logger.info(f"Number of ship ids found: {len(ship_ids)}")
        return ship_ids
    except requests.exceptions.RequestException as e:
        Logger.error(f"Error in ship IDs request: {e}", exc_info=True)
        return "server_error"