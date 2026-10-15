Feature: Bevakningen följer serverns livscykel
  Som användare av MCP-servern
  vill jag att servern startar direkt även när Bridge inte körs
  och att bevakningen stängs ner rent när servern avslutas.

  Scenario: Servern startar direkt även när Bridge är nere
    Given att Bridge inte går att nå
    When servern startar
    Then ska uppstarten ha gått på under en halv sekund
    And ska sessionen ha en bevakning av INBOX som inte är ansluten

  Scenario: Bevakningen startar med servern och stoppas när servern stängs
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    When servern startar
    Then ska bevakningen av INBOX ansluta
    When servern stängs
    Then ska inga bevakningsuppgifter vara kvar
    And ska Bridge inte ha några öppna anslutningar

  Scenario: Avstängd bevakning ansluter inte
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3
    And att PROTONMAIL_WATCH_ENABLED är false
    When servern startar
    Then ska sessionen ha en bevakning som är avstängd
    And ska Bridge inte ha fått någon anslutning
