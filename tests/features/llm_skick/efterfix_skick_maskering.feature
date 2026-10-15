Feature: Hemliga mottagare syns aldrig i serverns logg (stderr)
  Som användare som skickar med hemlig kopia
  vill jag att Bcc-adressen inte hamnar i klientens loggfil
  även när adressen har en citerad lokaldel eller felet är långt.

  Scenario: En vägrad Bcc med citerad lokaldel maskeras på stderr
    Given en SMTP-klient för ett konto med inställningen "allowed_recipients" satt till "@ok.se"
    When koden direkt i SMTP-klienten skickar ett mejl till "t@ok.se" med den hemliga kopian '"hemlig,bcc"@evil.com'
    Then ska anropet vägras med ett fel som nämner "evil.com"
    And ska granskningsraden på stderr inte innehålla "hemlig"
    And ska granskningsraden på stderr inte innehålla "evil.com"

  Scenario: Bcc som servern vägrar vid delvis leverans maskeras på stderr
    Given en SMTP-klient för ett konto utan begränsningar
    And Bridge vägrar mottagaren '"x(y"@evil.com'
    When koden direkt i SMTP-klienten skickar ett mejl till "t@ok.se" med den hemliga kopian '"x(y"@evil.com'
    Then ska granskningsraden på stderr inte innehålla "evil.com"
    And ska granskningsraden på stderr nämna att 1 av mottagarna vägrades
