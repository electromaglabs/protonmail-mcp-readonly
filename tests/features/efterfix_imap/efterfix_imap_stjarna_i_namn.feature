Feature: Mappnamn som innehåller "* " listas med rätt namn
  Som en MCP-klient
  vill jag att en mapp som heter "Folders/* Viktigt" listas med just det namnet,
  så att namnet jag får från list_mailboxes går att använda i nästa anrop.

  Scenario: En mapp med "* " i namnet listas oförändrad
    Given en riktig anslutning till en Bridge med mapparna "INBOX", "Folders/* Viktigt" och "Labels/a* b"
    When jag listar mapparna över anslutningen
    Then ska mapparna "INBOX", "Folders/* Viktigt" och "Labels/a* b" listas
    And ska ingen mapp heta "Folders/Viktigt"

  Scenario: Det listade namnet går att använda direkt
    Given en riktig anslutning till en Bridge med mapparna "INBOX", "Folders/* Viktigt" och "Labels/a* b"
    When jag listar mejlen i varje listad mapp över anslutningen
    Then ska varje mapp gå att öppna
