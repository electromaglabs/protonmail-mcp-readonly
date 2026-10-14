Feature: Behållare som Folders och Labels ger fel i stället för en tom mapp
  Som en MCP-klient
  vill jag få veta när jag frågar efter en behållare i stället för en mapp,
  eftersom Bridge svarar som om den vore en tom mapp.

  Scenario: Status för behållaren Folders
    Given att Bridge visar "Folders" som behållare
    When jag hämtar status för "Folders"
    Then ska verktyget ge ett fel som nämner "Folders är en behållare, inte en mapp"

  Scenario: Mejllistan för behållaren Labels
    Given att Bridge visar "Labels" som behållare
    When jag listar mejlen i "Labels"
    Then ska verktyget ge ett fel som nämner "Labels är en behållare, inte en mapp"

  Scenario: Sökning i en behållare
    Given att Bridge visar "Folders" som behållare
    When jag söker efter olästa mejl i "Folders"
    Then ska verktyget ge ett fel som nämner "är en behållare"

  Scenario: Ett mejl i en behållare
    Given att Bridge visar "Labels" som behållare
    When jag hämtar mejlet med UID "1" i "Labels"
    Then ska verktyget ge ett fel som nämner "är en behållare"

  Scenario: En vanlig tom mapp är fortfarande bara tom
    Given att Bridge visar "Folders" som behållare
    And att mappen "Folders/Tom" finns och är tom
    When jag hämtar status för "Folders/Tom"
    Then ska statusen vara 0 mejl och 0 olästa

  Scenario: En mapp med mejl kostar ingen extra listning
    Given att mejlet med UID "3" ligger i "INBOX"
    When jag listar mejlen i "INBOX"
    Then ska Bridge inte ha fått "LIST"
