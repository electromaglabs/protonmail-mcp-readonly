Feature: En mapp med undermappar tas inte bort av misstag
  Som en MCP-klient
  vill jag inte kunna ta bort en tom mapp vars undermappar innehåller mejl utan force,
  eftersom Bridge tar bort mappen utan att titta på undermapparna.

  Scenario: En tom mapp med en undermapp som har mejl tas inte bort
    Given att mappen "Folders/A" finns och är tom
    And att mejlet med UID "3" ligger i "Folders/A/B"
    When jag tar bort mappen "Folders/A"
    Then ska verktyget ge ett fel som nämner "Folders/A/B"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: En tom mapp med en tom undermapp tas inte heller bort
    Given att mappen "Folders/A" finns och är tom
    And att mappen "Folders/A/B" finns och är tom
    When jag tar bort mappen "Folders/A"
    Then ska verktyget ge ett fel som nämner "undermapp"
    And ska Bridge inte ha fått något skrivkommando

  Scenario: Med force tas mappen bort trots undermappar
    Given att mappen "Folders/A" finns och är tom
    And att mejlet med UID "3" ligger i "Folders/A/B"
    When jag tar bort mappen "Folders/A" med force
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "DELETE" med "Folders/A"

  Scenario: En mapp med liknande namn räknas inte som undermapp
    Given att mappen "Folders/A" finns och är tom
    And att mejlet med UID "3" ligger i "Folders/AB"
    And att mejlet med UID "4" ligger i "Folders/A B/C"
    When jag tar bort mappen "Folders/A"
    Then ska verktyget svara att det lyckades
    And ska Bridge ha fått "LIST" med "Folders/A/*"
