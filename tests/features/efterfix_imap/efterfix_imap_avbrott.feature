Feature: Ett avbrott mitt i ett anrop ger ett begripligt fel direkt
  Som användare av MCP-servern
  vill jag få veta direkt när anslutningen till Bridge bryts mitt i ett anrop,
  i stället för att vänta ut hela timeouten och få ett obegripligt fel.

  Scenario: Bridge startas om mellan sökningen och hämtningen
    Given en Bridge som stänger anslutningen efter svaret på "SEARCH"
    When jag söker efter olästa mejl med timeouten 5 sekunder
    Then ska jag få ett fel som säger att anslutningen bröts
    And ska felet komma inom 1 sekund

  Scenario: Bridge stängs i stället för att svara på en markering
    Given en Bridge som stänger anslutningen i stället för att svara på "UID STORE"
    When jag markerar mejl 1 som läst med timeouten 5 sekunder
    Then ska jag få ett fel som säger att anslutningen bröts
    And ska felet komma inom 1 sekund

  Scenario: Nästa anrop ansluter på nytt och fungerar
    Given en Bridge som stänger anslutningen efter svaret på "SEARCH"
    When jag söker efter olästa mejl med timeouten 5 sekunder
    And jag söker efter olästa mejl med timeouten 5 sekunder igen
    Then ska den andra sökningen ge 3 träffar
