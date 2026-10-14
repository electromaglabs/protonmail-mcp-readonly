Feature: Robust IMAP-anslutning mot ProtonMail Bridge
  Som användare av MCP-servern
  vill jag att mejlverktygen alltid arbetar i rätt mapp och återhämtar sig från anslutningsfel
  så att jag aldrig ändrar fel meddelande och aldrig behöver starta om servern.

  Scenario: Radering i en felstavad mapp rör inte meddelandet i den förra mappen
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att jag nyss har listat mejlen i "INBOX"
    When jag raderar meddelande 1 i mappen "Inkorgen-felstavad"
    Then ska jag få ett fel som säger att mappen "Inkorgen-felstavad" inte finns
    And ska inga flaggor ha ändrats på servern
    And ska en ny listning av "INBOX" visa 2 meddelanden

  Scenario: Sökning i en mapp som inte finns ger fel i stället för träffar från förra mappen
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att jag nyss har listat mejlen i "INBOX"
    When jag söker i mappen "Finns-inte"
    Then ska jag få ett fel som säger att mappen "Finns-inte" inte finns

  Scenario: Listning av en mapp som inte finns ger fel i stället för en tom mapp
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    When jag listar mejlen i "Finns-inte"
    Then ska jag få ett fel som säger att mappen "Finns-inte" inte finns

  Scenario: En nekad inloggning låser inte klienten
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att Bridge nekar inloggning
    When jag listar mejlen i "INBOX"
    Then ska jag få ett fel som säger att inloggningen misslyckades
    When Bridge åter godtar inloggning
    And jag listar mejlen i "INBOX"
    Then ska listningen visa 2 meddelanden

  Scenario: En inloggning som aldrig besvaras låser inte klienten
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att Bridge inte svarar på inloggning
    When jag listar mejlen i "INBOX"
    Then ska jag få ett timeoutfel
    When Bridge åter svarar på inloggning
    And jag listar mejlen i "INBOX"
    Then ska listningen visa 2 meddelanden

  Scenario: Ett anrop som avbryts mitt i inloggningen låser inte klienten
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att Bridge svarar på inloggning först efter en stund
    When anropet avbryts under inloggningen
    And Bridge har hunnit svara på inloggningen
    And jag listar mejlen i "INBOX"
    Then ska listningen visa 2 meddelanden

  Scenario: En flytt som Bridge aldrig besvarar låser inte servern
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And en Bridge med mappen "Archive" som innehåller 0 meddelanden
    And att Bridge aldrig svarar på "UID COPY"
    When jag flyttar meddelande 1 från "INBOX" till "Archive"
    Then ska jag få ett timeoutfel
    When jag listar mejlen i "INBOX"
    Then ska listningen visa 2 meddelanden

  Scenario: Återanslutning lämnar inga gamla anslutningar öppna
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att jag nyss har listat mejlen i "INBOX"
    And att Bridge aldrig svarar på "NOOP"
    When jag listar mejlen i "INBOX" 3 gånger
    Then ska listningen visa 2 meddelanden
    And ska Bridge ha högst 1 öppen anslutning

  Scenario: Bridge som inte körs ger ett tydligt fel direkt
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att Bridge inte körs
    When jag listar mejlen i "INBOX"
    Then ska jag få ett fel som säger att Bridge inte går att nå
    And ska anropet ha tagit under 150 ms

  Scenario: Efter en omstart av Bridge återansluter nästa anrop direkt
    Given en Bridge med mappen "INBOX" som innehåller 2 meddelanden
    And att jag nyss har listat mejlen i "INBOX"
    When Bridge startas om
    And jag listar mejlen i "INBOX"
    Then ska listningen visa 2 meddelanden
    And ska anropet ha tagit under 150 ms
