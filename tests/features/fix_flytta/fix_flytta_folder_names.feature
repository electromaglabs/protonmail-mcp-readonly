Feature: Skapa och byta namn på mappar och etiketter
  Som en MCP-klient
  vill jag få veta direkt varför ett mappnamn inte fungerar hos Proton
  i stället för ett tyst "false" från Bridge.

  Scenario: Skapa en mapp under Folders
    When jag skapar mappen "Folders/Projekt"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "CREATE" med "Folders/Projekt"

  Scenario: Skapa en etikett under Labels
    When jag skapar mappen "Labels/Kvitton"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "CREATE" med "Labels/Kvitton"

  Scenario: Namn utan Folders/ eller Labels/ avvisas med en förklaring
    When jag skapar mappen "Projekt"
    Then ska verktyget ge ett fel som nämner "Folders/"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Underetiketter finns inte i Proton
    When jag skapar mappen "Labels/Jobb/Kunder"
    Then ska verktyget ge ett fel som nämner "Underetiketter"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: En mapp kan inte döpas om till en etikett
    When jag byter namn på "Folders/Projekt" till "Labels/Projekt"
    Then ska verktyget ge ett fel som nämner "mellan mapp och etikett"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Systemmappar kan inte döpas om
    When jag byter namn på "INBOX" till "Folders/Inkorg"
    Then ska verktyget ge ett fel som nämner "Folders/"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Om Bridge nekar får klienten veta varför
    Given att Bridge nekar CREATE med "parent folder does not exist"
    When jag skapar mappen "Folders/A/B"
    Then ska verktyget ge ett fel som nämner "parent folder does not exist"
