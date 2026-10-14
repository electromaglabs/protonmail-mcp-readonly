Feature: Ta bort en mapp eller etikett
  Som en MCP-klient
  vill jag inte kunna ta bort en mapp med mejl i av misstag,
  eftersom Bridge tar bort den ändå och en etikett då försvinner från alla mejl.

  Scenario: En tom mapp tas bort
    Given att mappen "Folders/Gammalt" finns och är tom
    When jag tar bort mappen "Folders/Gammalt"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "DELETE" med "Folders/Gammalt"

  Scenario: En mapp med mejl tas inte bort
    Given att mejlet med UID "3" ligger i "Folders/Projekt"
    When jag tar bort mappen "Folders/Projekt"
    Then ska verktyget ge ett fel som nämner "inte tom"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: En etikett med mejl tas bort när jag uttryckligen ber om det
    Given att mejlet med UID "3" ligger i "Labels/Kvitton"
    When jag tar bort mappen "Labels/Kvitton" med force
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "DELETE" med "Labels/Kvitton"

  Scenario: En mapp som inte finns ger ett tydligt fel
    When jag tar bort mappen "Folders/Finns-inte"
    Then ska verktyget ge ett fel som nämner "Folders/Finns-inte"
    And ska Bridge inte ha fått något skrivkommando
