import requests
import datetime
import html
import json
import os
import re
import sys
import statistics
from pathlib import Path
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# ================= ENV =================
BOT_TOKEN = os.getenv("PREDICTIONS_BOT_TOKEN") or os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("PREDICTIONS_CHANNEL_ID")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DRY_RUN = os.getenv("DRY_RUN", "").lower() in {"1", "true", "yes", "oui"}
FORCE_RUN = os.getenv("FORCE_RUN", "").lower() in {"1", "true", "yes", "oui"}
STATE_FILE = Path(os.getenv("PREDICTIONS_STATE_FILE", ".state/predictions.json"))
LOCAL_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Africa/Lome"))


def local_today() -> datetime.date:
    return datetime.datetime.now(LOCAL_TIMEZONE).date()


def validate_configuration() -> bool:
    if DRY_RUN:
        return True
    missing = []
    if not BOT_TOKEN:
        missing.append("PREDICTIONS_BOT_TOKEN ou BOT_TOKEN")
    if not CHANNEL_ID:
        missing.append("PREDICTIONS_CHANNEL_ID")
    if missing:
        print("❌ Secret(s) GitHub manquant(s): " + ", ".join(missing))
        return False
    return True


def already_published_today() -> bool:
    if FORCE_RUN or not STATE_FILE.exists():
        return False
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return payload.get("last_successful_date") == local_today().isoformat()
    except (OSError, json.JSONDecodeError, AttributeError):
        return False


def save_successful_run() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    temporary.write_text(
        json.dumps({"last_successful_date": local_today().isoformat()}, indent=2),
        encoding="utf-8",
    )
    temporary.replace(STATE_FILE)

# ================= CONFIG =================
LEAGUES = [
    "uefa.champions",
    "eng.1",
    "esp.1", 
    "ita.1",
    "ger.1",
    "fra.1",
    "por.1",
    "ned.1"
]

BIG_TEAMS = [
    "Real Madrid", "Barcelona", "Manchester City", "Bayern Munich",
    "Paris Saint-Germain", "Liverpool", "Arsenal", "Inter",
    "Juventus", "AC Milan", "Chelsea", "Borussia Dortmund"
]

# Facteurs de pondération pour l'analyse locale
WEIGHTS = {
    "home_advantage": 1.2,
    "big_team": 0.8,
    "form_recent": 1.5,
    "goals_difference": 0.3,
    "champions_league": 0.9  # Réduit les nuls en Champions
}

# ================= DATA CLASSES =================
@dataclass
class TeamForm:
    wins: int
    draws: int
    losses: int
    gf: int
    ga: int
    matches_analyzed: int
    
    @property
    def points_per_game(self) -> float:
        if self.matches_analyzed == 0:
            return 1.5  # Moyenne par défaut
        return (self.wins * 3 + self.draws) / self.matches_analyzed
    
    @property
    def goal_difference_per_game(self) -> float:
        if self.matches_analyzed == 0:
            return 0.0
        return (self.gf - self.ga) / self.matches_analyzed
    
    @property
    def attack_strength(self) -> float:
        if self.matches_analyzed == 0:
            return 1.5
        return self.gf / self.matches_analyzed
    
    @property
    def defense_strength(self) -> float:
        if self.matches_analyzed == 0:
            return 1.5
        return self.ga / self.matches_analyzed

@dataclass
class MatchPrediction:
    home_team: str
    away_team: str
    prediction: str
    confidence: float
    odds: float
    analysis_text: str
    league: str
    score_probable: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "home": self.home_team,
            "away": self.away_team,
            "pick": self.get_pick_text(),
            "confidence": self.confidence,
            "odds": self.odds,
            "analysis": self.analysis_text,
            "league": self.league,
            "score": self.score_probable
        }
    
    def get_pick_text(self) -> str:
        if self.prediction == "home_win":
            return f"{self.home_team} gagne"
        elif self.prediction == "away_win":
            return f"{self.away_team} gagne"
        else:
            return "Match nul"

# ================= UTILS =================
def log(msg: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    sys.stdout.flush()

def send_telegram(message: str) -> bool:
    """Send message to Telegram channel"""
    if DRY_RUN:
        log("[DRY RUN] Message Telegram simulé")
        print(message)
        return True

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHANNEL_ID,
            "text": message[:4096],
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }, timeout=20)
        r.raise_for_status()
        log(f"[TELEGRAM] Message envoyé (status={r.status_code})")
        return True
    except requests.exceptions.RequestException as e:
        log(f"[ERROR TELEGRAM] Erreur d'envoi: {e}")
        # Essayer sans HTML en fallback
        try:
            plain_message = html.unescape(re.sub(r"<[^>]+>", "", message))
            r = requests.post(url, json={
                "chat_id": CHANNEL_ID,
                "text": plain_message[:4096]
            }, timeout=20)
            r.raise_for_status()
            log(f"[TELEGRAM Fallback] status={r.status_code}")
            return True
        except requests.exceptions.RequestException:
            return False

def get_matches_today(league: str) -> List[Dict]:
    """Get today's matches for a specific league"""
    today = local_today().strftime("%Y%m%d")
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={today}"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        events = data.get("events", [])
        log(f"[INFO] {league} → {len(events)} match(s) trouvé(s)")
        return events
    except requests.exceptions.RequestException as e:
        log(f"[ERROR] {league} → Erreur réseau: {e}")
        return []
    except ValueError as e:
        log(f"[ERROR] {league} → Erreur JSON: {e}")
        return []

def get_team_form(team_id: str, league: str) -> TeamForm:
    """Get team form from last 5 matches"""
    url = f"https://site.web.api.espn.com/apis/site/v2/sports/soccer/{league}/teams/{team_id}/schedule"
    
    wins = draws = losses = gf = ga = 0
    matches_analyzed = 0
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        events = data.get("events", [])
        if not events:
            return TeamForm(0, 0, 0, 0, 0, 0)
        
        completed_matches = []
        for e in events:
            try:
                status_type = e.get("status", {}).get("type", {})
                if status_type.get("completed") == True or status_type.get("id") == "3":
                    completed_matches.append(e)
            except:
                continue
        
        for e in completed_matches[:5]:
            try:
                comp = e.get("competitions", [{}])[0].get("competitors", [])
                if len(comp) < 2:
                    continue
                    
                h, a = comp[0], comp[1]
                h_score = int(h.get("score", "0"))
                a_score = int(a.get("score", "0"))
                
                if h.get("team", {}).get("id") == team_id:
                    sf, sa = h_score, a_score
                else:
                    sf, sa = a_score, h_score
                
                gf += sf
                ga += sa
                
                if sf > sa:
                    wins += 1
                elif sf < sa:
                    losses += 1
                else:
                    draws += 1
                    
                matches_analyzed += 1
            except Exception:
                continue
                
    except Exception as e:
        log(f"[WARN] Erreur get_team_form pour {team_id}: {e}")
    
    return TeamForm(wins, draws, losses, gf, ga, matches_analyzed)

# ================= LOCAL ANALYSIS (INTELLIGENT FALLBACK) =================
def analyze_match_locally(
    home_team: str,
    away_team: str,
    home_form: TeamForm,
    away_form: TeamForm,
    league: str
) -> Tuple[str, float, str, str]:
    """
    Analyse locale intelligente basée sur les statistiques
    Retourne: (prediction, confidence, analysis_text, probable_score)
    """
    
    is_home_big = home_team in BIG_TEAMS
    is_away_big = away_team in BIG_TEAMS
    is_champions = "champions" in league
    
    # Calcul des forces de base
    home_strength = (
        home_form.points_per_game * WEIGHTS["form_recent"] +
        home_form.goal_difference_per_game * WEIGHTS["goals_difference"] +
        (WEIGHTS["home_advantage"] if not is_champions else WEIGHTS["home_advantage"] * 0.9) +
        (WEIGHTS["big_team"] if is_home_big else 0)
    )
    
    away_strength = (
        away_form.points_per_game * WEIGHTS["form_recent"] +
        away_form.goal_difference_per_game * WEIGHTS["goals_difference"] +
        (WEIGHTS["big_team"] if is_away_big else 0)
    )
    
    # Calcul des attaques/défenses attendues
    home_attack = home_form.attack_strength
    home_defense = home_form.defense_strength
    away_attack = away_form.attack_strength
    away_defense = away_form.defense_strength
    
    # Buts attendus (formule Poisson simplifiée)
    expected_home_goals = max(0.1, (home_attack + away_defense) / 2)
    expected_away_goals = max(0.1, (away_attack + home_defense) / 2)
    
    # Probabilités des résultats
    # Victoire domicile
    if home_strength > away_strength * 1.3:
        prediction = "home_win"
        base_confidence = 7.5 + min(2.0, (home_strength - away_strength) * 2)
    elif away_strength > home_strength * 1.3:
        prediction = "away_win"
        base_confidence = 7.5 + min(2.0, (away_strength - home_strength) * 2)
    else:
        # Match équilibré
        diff = abs(home_strength - away_strength)
        if diff < 0.5:
            prediction = "draw"
            base_confidence = 6.0
        elif home_strength > away_strength:
            prediction = "home_win"
            base_confidence = 6.5
        else:
            prediction = "away_win"
            base_confidence = 6.5
    
    # Ajustement Champions League (moins de nuls)
    if is_champions and prediction == "draw":
        base_confidence *= 0.8
        # Réévaluer si très équilibré
        if home_strength > away_strength:
            prediction = "home_win"
            base_confidence = 6.0
        else:
            prediction = "away_win"
            base_confidence = 6.0
    
    # Score probable
    if prediction == "home_win":
        home_score = int(round(expected_home_goals + 0.3))
        away_score = int(round(expected_away_goals - 0.2))
        score = f"{max(1, home_score)}-{max(0, away_score)}"
    elif prediction == "away_win":
        home_score = int(round(expected_home_goals - 0.2))
        away_score = int(round(expected_away_goals + 0.3))
        score = f"{max(0, home_score)}-{max(1, away_score)}"
    else:
        home_score = int(round(expected_home_goals))
        away_score = int(round(expected_away_goals))
        score = f"{home_score}-{away_score}"
    
    # Éviter les scores improbables
    if home_score > 5: home_score = 5
    if away_score > 5: away_score = 5
    score = f"{home_score}-{away_score}"
    
    # Génération de l'analyse textuelle
    analysis_parts = []
    
    if home_form.matches_analyzed >= 3:
        form_desc = []
        if home_form.wins > 2:
            form_desc.append("excellente forme")
        elif home_form.wins >= 1:
            form_desc.append("bonne forme")
        else:
            form_desc.append("forme difficile")
        
        if away_form.wins > 2:
            form_desc.append("excellente forme")
        elif away_form.wins >= 1:
            form_desc.append("bonne forme")
        else:
            form_desc.append("forme difficile")
        
        if form_desc:
            analysis_parts.append(f"Forme: {home_team} en {form_desc[0]}, {away_team} en {form_desc[1]}.")
    
    if is_home_big or is_away_big:
        big_teams = []
        if is_home_big:
            big_teams.append(home_team)
        if is_away_big:
            big_teams.append(away_team)
        analysis_parts.append(f"Grosse(s) équipe(s): {', '.join(big_teams)}.")
    
    goal_diff = home_form.gf - home_form.ga - (away_form.gf - away_form.ga)
    if abs(goal_diff) > 5:
        analysis_parts.append("Différence de buts significative en faveur du " + 
                            ("domicile" if goal_diff > 0 else "extérieur"))
    
    # Analyse spécifique selon la prédiction
    if prediction == "home_win":
        analysis_parts.append(f"Avantage domicile et supériorité statistique pour {home_team}.")
    elif prediction == "away_win":
        analysis_parts.append(f"{away_team} montre des arguments pour l'emporter à l'extérieur.")
    else:
        analysis_parts.append("Match très équilibré, nul probable.")
    
    analysis_text = " ".join(analysis_parts)
    if not analysis_text:
        analysis_text = f"Match {league} entre {home_team} et {away_team}. Données statistiques analysées."
    
    # Confiance finale (entre 4 et 9)
    confidence = max(4.0, min(9.0, base_confidence))
    
    return prediction, confidence, analysis_text, score

# ================= DEEPSEEK ANALYSIS (OPTIONNEL) =================
def analyze_match_with_deepseek(
    home_team: str,
    away_team: str,
    home_form: TeamForm,
    away_form: TeamForm,
    league: str
) -> Tuple[str, float, str, str]:
    """Analyze match using DeepSeek API (if available)"""
    
    if not DEEPSEEK_API_KEY:
        return analyze_match_locally(home_team, away_team, home_form, away_form, league)
    
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )
        
        prompt = f"""
        Analyse ce match de football et donne:
        1. PRONOSTIC: home_win / away_win / draw
        2. CONFIDENCE: score de 1 à 10
        3. SCORE: score probable (ex: 2-1)
        4. ANALYSE: analyse courte en français
        
        Match: {home_team} vs {away_team}
        Ligue: {league}
        
        Forme {home_team} (5 derniers): {home_form.wins}V, {home_form.draws}N, {home_form.losses}D
        Buts: {home_form.gf} pour, {home_form.ga} contre
        
        Forme {away_team} (5 derniers): {away_form.wins}V, {away_form.draws}N, {away_form.losses}D
        Buts: {away_form.gf} pour, {away_form.ga} contre
        
        Grosse équipe: {home_team in BIG_TEAMS} / {away_team in BIG_TEAMS}
        
        Réponds exactement dans ce format:
        PRONOSTIC: ...
        CONFIDENCE: ...
        SCORE: ...
        ANALYSE: ...
        """
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Expert en analyse footballistique. Sois concis et précis."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=200
        )
        
        result = response.choices[0].message.content.strip()
        lines = result.split('\n')
        
        prediction = "draw"
        confidence = 5.0
        score = "1-1"
        analysis = "Analyse IA"
        
        for line in lines:
            if line.startswith("PRONOSTIC:"):
                pred = line.replace("PRONOSTIC:", "").strip().lower()
                if pred in ["home_win", "away_win", "draw"]:
                    prediction = pred
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf = float(line.replace("CONFIDENCE:", "").strip())
                    confidence = max(1.0, min(10.0, conf))
                except:
                    pass
            elif line.startswith("SCORE:"):
                score = line.replace("SCORE:", "").strip()
            elif line.startswith("ANALYSE:"):
                analysis = line.replace("ANALYSE:", "").strip()
        
        return prediction, confidence, analysis, score
        
    except Exception as e:
        log(f"[WARN] DeepSeek non disponible: {e}")
        # Fallback sur l'analyse locale
        return analyze_match_locally(home_team, away_team, home_form, away_form, league)

def calculate_odds(prediction: str, confidence: float, home_big: bool, away_big: bool) -> float:
    """Calculate realistic odds"""
    # Base odds: plus la confiance est haute, plus la cote est basse
    base_odds = 11.0 - confidence  # Si confiance=7 → cote=4.0
    
    # Ajustements
    if prediction == "home_win" and home_big:
        base_odds *= 0.7  # Grosse équipe favorite → cote plus basse
    elif prediction == "away_win" and away_big:
        base_odds *= 0.7
    elif prediction == "draw":
        base_odds *= 1.3  # Les nuls ont souvent des cotes plus élevées
    
    # Limites réalistes
    odds = max(1.5, min(8.0, round(base_odds, 2)))
    return odds

def predict_match(
    home_team: str,
    away_team: str,
    home_form: TeamForm,
    away_form: TeamForm,
    league: str
) -> MatchPrediction:
    """Create match prediction"""
    
    # Utiliser DeepSeek si disponible, sinon analyse locale
    if DEEPSEEK_API_KEY:
        prediction, confidence, analysis, score = analyze_match_with_deepseek(
            home_team, away_team, home_form, away_form, league
        )
    else:
        prediction, confidence, analysis, score = analyze_match_locally(
            home_team, away_team, home_form, away_form, league
        )
    
    # Calcul des cotes
    is_home_big = home_team in BIG_TEAMS
    is_away_big = away_team in BIG_TEAMS
    odds = calculate_odds(prediction, confidence, is_home_big, is_away_big)
    
    # Format de la ligue
    league_parts = league.split(".")
    if len(league_parts) > 1:
        league_name = league_parts[0].upper()
    else:
        league_name = league.upper()
    
    return MatchPrediction(
        home_team=home_team,
        away_team=away_team,
        prediction=prediction,
        confidence=confidence,
        odds=odds,
        analysis_text=analysis[:200],  # Limiter la longueur
        league=league_name,
        score_probable=score
    )

# ================= DIVERSIFICATION =================
def diversify_predictions(predictions: List[MatchPrediction]) -> List[MatchPrediction]:
    """Ensure we don't have too many draws"""
    if len(predictions) < 3:
        return predictions
    
    draw_count = sum(1 for p in predictions if p.prediction == "draw")
    max_draws = max(1, len(predictions) // 3)  # Max 33% de nuls
    
    if draw_count <= max_draws:
        return predictions
    
    # Trier par confiance (les moins confiants en premier pour modification)
    sorted_preds = sorted(predictions, key=lambda x: x.confidence)
    
    for pred in sorted_preds:
        if pred.prediction == "draw" and draw_count > max_draws:
            # Changer en victoire domicile (simplifié)
            pred.prediction = "home_win"
            pred.confidence *= 0.85  # Réduire la confiance après modification
            # Recalculer la cote
            is_home_big = pred.home_team in BIG_TEAMS
            is_away_big = pred.away_team in BIG_TEAMS
            pred.odds = calculate_odds("home_win", pred.confidence, is_home_big, is_away_big)
            pred.analysis_text = "Match initialement équilibré, léger avantage domicile."
            pred.score_probable = "1-0"
            draw_count -= 1
        
        if draw_count <= max_draws:
            break
    
    return predictions

# ================= FORMATTING =================
def format_combo_message(title: str, predictions: List[MatchPrediction], risk_level: str) -> str:
    """Format combo message for Telegram"""
    if not predictions:
        return f"<b>{html.escape(title)}</b>\n\nAucun pronostic {html.escape(risk_level)} aujourd'hui."
    
    source = "DeepSeek AI" if DEEPSEEK_API_KEY else "Analyse Statistique"
    
    message = f"<b>{html.escape(title)}</b>\n"
    message += f"📅 {local_today().strftime('%d/%m/%Y')}\n"
    message += f"🤖 {source}\n"
    message += f"🎯 {len(predictions)} sélection(s)\n\n"
    
    total_odds = 1.0
    
    for i, pred in enumerate(predictions, 1):
        total_odds *= pred.odds
        safe_home = html.escape(pred.home_team)
        safe_away = html.escape(pred.away_team)
        safe_league = html.escape(pred.league)
        safe_analysis = html.escape(pred.analysis_text[:80])
        
        # Emoji selon le pronostic
        if pred.prediction == "draw":
            outcome_emoji = "⚖️ NUL"
        elif pred.prediction == "home_win":
            outcome_emoji = "🏠 DOMICILE"
        else:
            outcome_emoji = "✈️ EXTERIEUR"
        
        # Étoiles de confiance
        stars = min(5, int(pred.confidence / 2))
        conf_bars = "★" * stars + "☆" * (5 - stars)
        
        # Message court
        message += (
            f"{i}. <b>{safe_home} - {safe_away}</b>\n"
            f"   {outcome_emoji} | {conf_bars} ({pred.confidence:.1f}/10)\n"
            f"   📊 {safe_league} | 🎯 {html.escape(pred.score_probable)} | 💰 <b>{pred.odds}</b>\n"
            f"   <i>{safe_analysis}...</i>\n\n"
        )
    
    # Calcul de la mise recommandée
    if risk_level == "MEDIUM":
        stake = min(15, max(3, round(25 / total_odds, 2)))
    else:
        stake = min(8, max(1, round(15 / total_odds, 2)))
    
    potential_win = round(stake * total_odds, 2)
    roi = round((potential_win - stake) / stake * 100, 1)
    
    message += (
        f"<b>📈 RÉCAPITULATIF</b>\n"
        f"• Cote combinée: <b>{round(total_odds, 2)}</b>\n"
        f"• Mise conseillée: <b>{stake}€</b>\n"
        f"• Gain potentiel: <b>{potential_win}€</b> (+{roi}%)\n\n"
        f"<i>⚠️ Paris responsables | Résultats basés sur analyse statistique</i>"
    )
    
    return message

# ================= MAIN =================
def main() -> int:
    if not validate_configuration():
        return 1
    if already_published_today():
        log("ℹ️ Les pronostics du jour ont déjà été publiés. Utilisez FORCE_RUN=1 pour recommencer.")
        return 0

    log("🚀 Bot de pronostics avancé démarré")
    
    all_predictions = []
    
    log("📊 Collecte des matchs du jour...")
    
    for league in LEAGUES:
        events = get_matches_today(league)
        
        for match in events:
            try:
                comp = match.get("competitions", [{}])[0]
                competitors = comp.get("competitors", [])
                
                if len(competitors) < 2:
                    continue
                
                h = next((item for item in competitors if item.get("homeAway") == "home"), competitors[0])
                a = next((item for item in competitors if item.get("homeAway") == "away"), competitors[1])
                home_team = h.get("team", {}).get("displayName", "Inconnu")
                away_team = a.get("team", {}).get("displayName", "Inconnu")
                home_id = h.get("team", {}).get("id")
                away_id = a.get("team", {}).get("id")
                
                if not home_id or not away_id:
                    continue
                
                # Vérifier si le match n'a pas encore commencé
                status = match.get("status", {}).get("type", {})
                if status.get("id") != "1":  # 1 = programmé
                    log(f"[SKIP] {home_team} vs {away_team} - Match déjà commencé")
                    continue
                
                # Obtenir les formes des équipes
                log(f"[ANALYSE] {home_team} vs {away_team}")
                home_form = get_team_form(home_id, league)
                away_form = get_team_form(away_id, league)
                
                # Générer la prédiction
                prediction = predict_match(home_team, away_team, home_form, away_form, league)
                all_predictions.append(prediction)
                
                log(f"[PRONO] {home_team} vs {away_team}: {prediction.get_pick_text()} ({prediction.confidence:.1f}/10)")
                
            except Exception as e:
                log(f"[ERROR] Traitement match: {e}")
                continue
    
    if not all_predictions:
        log("❌ Aucun match à analyser aujourd'hui")
        if send_telegram("ℹ️ <b>Aucun match programmé aujourd'hui</b> dans les ligues suivies."):
            if not DRY_RUN:
                save_successful_run()
            return 0
        return 1
    
    # Trier par confiance
    all_predictions.sort(key=lambda x: x.confidence, reverse=True)
    
    # Sélectionner les pronostics MEDIUM (confiance >= 6.0)
    medium_predictions = [p for p in all_predictions if p.confidence >= 6.0][:3]
    
    # Sélectionner les pronostics RISK (confiance >= 4.5)
    remaining = [p for p in all_predictions if p not in medium_predictions and p.confidence >= 4.5]
    risk_predictions = remaining[:5]
    risk_predictions = diversify_predictions(risk_predictions)
    
    # Envoyer les messages Telegram
    send_results = []

    if medium_predictions:
        send_results.append(send_telegram(format_combo_message("🔵 COMBINÉ SÉCURISÉ", medium_predictions, "MEDIUM")))
        log(f"✅ {len(medium_predictions)} pronostic(s) MEDIUM envoyé(s)")
    else:
        send_results.append(send_telegram("ℹ️ <b>Aucun pronostic sécurisé aujourd'hui</b>\n(Seuil de confiance: ≥6.0/10)"))
        log("⚠️ Aucun pronostic MEDIUM (confiance < 6.0)")
    
    if risk_predictions:
        send_results.append(send_telegram(format_combo_message("🔴 COMBINÉ RISK", risk_predictions, "RISK")))
        log(f"✅ {len(risk_predictions)} pronostic(s) RISK envoyé(s)")
    else:
        send_results.append(send_telegram("ℹ️ <b>Aucun pronostic risk aujourd'hui</b>\n(Seuil de confiance: ≥4.5/10)"))
        log("⚠️ Aucun pronostic RISK (confiance < 4.5)")
    
    # Statistiques
    avg_conf = statistics.mean([p.confidence for p in all_predictions]) if all_predictions else 0
    
    stats_msg = (
        f"📊 <b>STATISTIQUES DU JOUR</b>\n"
        f"├ Matchs analysés: {len(all_predictions)}\n"
        f"├ Pronostics sécurisés: {len(medium_predictions)}\n"
        f"├ Pronostics risk: {len(risk_predictions)}\n"
        f"├ Confiance moyenne: {avg_conf:.1f}/10\n"
        f"└ Source: {'DeepSeek AI' if DEEPSEEK_API_KEY else 'Analyse Statistique'}\n\n"
        f"🔄 Prochaine analyse demain."
    )
    send_results.append(send_telegram(stats_msg))
    
    log(f"✅ Analyse terminée! {len(all_predictions)} match(s) analysé(s)")
    if all(send_results):
        if not DRY_RUN:
            save_successful_run()
        return 0
    log("❌ Au moins un message Telegram n'a pas pu être envoyé.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
