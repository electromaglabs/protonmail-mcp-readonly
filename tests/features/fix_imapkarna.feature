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
