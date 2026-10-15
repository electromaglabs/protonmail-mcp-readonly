Feature: Bevakningen väntar allt längre när Bridge inte låter den köra IDLE
  Som användare som har Bridge igång hela dagen
  vill jag att bevakningen backar undan när IDLE inte fungerar
  så att den inte loggar in mot Bridge varje sekund i all evighet.

  Väntetiden börjar om först när en IDLE-omgång har gått klart, inte redan
  när inloggningen och SELECT lyckats.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3

  Scenario: Väntetiden växer när Bridge nekar IDLE
    Given att Bridge nekar IDLE
    When bevakningen av INBOX startas med väntetiden 1 sekund och taket 4 sekunder
    Then ska väntetiderna mellan försöken börja med 1, 2, 4, 4 sekunder
    And ska bevakningen aldrig ha sagt att INBOX bevakas
    And ska felet bara ha loggats som varning en gång

  Scenario: Väntetiden växer när Bridge bryter IDLE direkt
    Given att Bridge stänger anslutningen direkt efter att IDLE börjat
    When bevakningen av INBOX startas med väntetiden 1 sekund och taket 4 sekunder
    Then ska väntetiderna mellan försöken börja med 1, 2, 4, 4 sekunder

  Scenario: Väntetiden börjar om när en IDLE-omgång har gått klart
    Given att Bridge nekar IDLE de två första gångerna
    When bevakningen av INBOX startas med väntetiden 1 sekund, taket 4 sekunder och förnyelse var 0.1 sekund
    And en IDLE-omgång har gått klart
    And Bridge startas om
    Then ska väntetiderna mellan försöken börja med 1, 2, 1 sekunder
