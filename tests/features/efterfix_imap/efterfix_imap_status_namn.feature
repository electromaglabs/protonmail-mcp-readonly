Feature: Antalet mejl läses ur STATUS-svaret, inte ur mappnamnet
  Som en MCP-klient
  vill jag att skyddet mot att ta bort en mapp med mejl gäller oavsett vad mappen heter,
  eftersom Bridge skriver mappnamnet på samma rad som antalet.

  Scenario: En mapp som heter "Messages 0" och har mejl tas inte bort
    Given att mejlet med UID "3" ligger i "Folders/Messages 0"
    And att mejlet med UID "4" ligger i "Folders/Messages 0"
    When jag tar bort mappen "Folders/Messages 0"
    Then ska verktyget ge ett fel som nämner "inte tom (2 mejl)"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: En tom mapp som heter "Messages 2024" tas bort
    Given att mappen "Folders/Messages 2024" finns och är tom
    When jag tar bort mappen "Folders/Messages 2024"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "DELETE" med "Folders/Messages 2024"

  Scenario: Status för en mapp vars namn liknar ett STATUS-svar
    Given att mejlet med UID "3" ligger i "Folders/x (MESSAGES 9 UNSEEN 9)"
    When jag hämtar status för "Folders/x (MESSAGES 9 UNSEEN 9)"
    Then ska statusen vara 1 mejl och 0 olästa
