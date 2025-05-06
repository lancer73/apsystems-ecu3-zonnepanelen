# Installatiehandleiding Zonnepanelen Home Assistant Integratie

Deze integratie haalt gegevens op van je zonnepanelen systeem door middel van de webinterface die beschikbaar is op je lokale netwerk. De integratie is gebaseerd op het Python script dat je hebt gedeeld.

## Bestanden en structuur

Voor een custom component in Home Assistant heb je de volgende structuur nodig:

```
config/custom_components/zonnepanelen/
├── __init__.py
├── const.py
├── config_flow.py
├── manifest.json
├── sensor.py
├── strings.json
└── translations/
    └── en.json
```

## Installatie stappen

1. Maak een map `custom_components` aan in je Home Assistant configuratiemap als deze nog niet bestaat.
2. Maak een submap `zonnepanelen` aan in de `custom_components` map.
3. Kopieer alle gegenereerde bestanden naar de juiste locatie:
   - `__init__.py` naar `config/custom_components/zonnepanelen/`
   - `const.py` naar `config/custom_components/zonnepanelen/`
   - `config_flow.py` naar `config/custom_components/zonnepanelen/`
   - `manifest.json` naar `config/custom_components/zonnepanelen/`
   - `sensor.py` naar `config/custom_components/zonnepanelen/`
   - `strings.json` naar `config/custom_components/zonnepanelen/`
   - Maak een map `translations` aan in `config/custom_components/zonnepanelen/`
   - Kopieer `en.json` naar `config/custom_components/zonnepanelen/translations/`

4. Herstart Home Assistant.
5. Ga naar Instellingen -> Apparaten & Diensten -> Integraties en klik op "Integratie toevoegen".
6. Zoek naar "Zonnepanelen" en selecteer deze.
7. Voer het IP-adres of de hostname in van je zonnepanelen webinterface (zonder "http://"), geef een naam op en stel eventueel een aangepast vernieuwingsinterval in.

## Configuratie

Je kunt de integratie op twee manieren configureren:

### 1. Via de gebruikersinterface (aanbevolen)

Zoals hierboven beschreven, voeg je de integratie toe via de Home Assistant UI.

### 2. Via configuration.yaml

Als alternatief kun je de integratie configureren in je `configuration.yaml` bestand:

```yaml
zonnepanelen:
  host: 192.168.107.107  # IP-adres of hostname zonder http://
  name: Zonnepanelen     # optioneel, standaard is "Zonnepanelen"
  scan_interval: 60      # optioneel, standaard is 60 seconden
```

## Wat krijg je?

Na installatie zal de integratie verschillende sensoren toevoegen aan Home Assistant:

1. **Systeem sensoren:**
   - Zonnepanelen State - De huidige status van het systeem
   - Zonnepanelen Lifetime Energy - Totale opgewekte energie sinds installatie
   - Zonnepanelen Daily Energy - Vandaag opgewekte energie
   - Zonnepanelen Online Inverters - Aantal actieve omvormers
   - Zonnepanelen Signal Strength - Signaalsterkte

2. **Paneel-specifieke sensoren:**
   Voor elk paneel of omvormer dat wordt gedetecteerd, worden er sensoren aangemaakt voor:
   - Vermogen (Power)
   - Voltage (Volt)
   - Frequentie (Frequency), indien beschikbaar
   - Temperatuur (Temperature), indien beschikbaar

## Problemen oplossen

Als je problemen ondervindt bij het installeren of gebruiken van deze integratie:

1. **Controleer de logs:** Ga naar Instellingen -> Systeem -> Logs en zoek naar "zonnepanelen" om relevante logmeldingen te vinden.
2. **Controleer de verbinding:** Zorg ervoor dat je het juiste IP-adres hebt opgegeven en dat je Home Assistant-installatie toegang heeft tot dit adres.
3. **Herstart Home Assistant:** Soms is een herstart nodig om wijzigingen door te voeren.

## Aanpassingen

Als de webinterface van je zonnepanelen systeem afwijkt van het formaat dat in deze integratie wordt verwacht, moet je mogelijk aanpassingen maken aan de manier waarop gegevens worden opgehaald in de `fetch_data` methode in het `__init__.py` bestand.

De huidige implementatie is gebaseerd op het door jou gedeelde script en verwacht HTML pagina's in een specifiek formaat. Als de structuur van de webpagina's anders is, moet je mogelijk de regex patronen aanpassen.
