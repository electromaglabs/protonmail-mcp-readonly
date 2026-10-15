Feature: Servern märker när nya mejl kommer
  Som modell som hjälper användaren med mejlen
  vill jag få veta när ett nytt mejl kommer in utan att fråga Bridge om och om igen
  så att jag kan reagera direkt, utan att något markeras som läst.

  Bevakningen kör IMAP IDLE i egna anslutningar, en per mapp, aldrig i den
  delade anslutningen som verktygen använder. Bridge kopplar ner en IDLE som
  varat i 29 minuter, så den förnyas före det.

  Background:
    Given en Bridge med IDLE där INBOX har mejlen 1, 2 och 3

  Scenario: Ett nytt mejl ger en händelse till lyssnarna
    Given att bevakningen av INBOX har startat
    When ett mejl med ämnet "Offert" kommer till INBOX
    Then ska lyssnaren ha fått mejlet med UID 4 i INBOX med ämnet "Offert"
    And ska händelsekön för INBOX innehålla UID 4

  Scenario: Mejl som fanns när bevakningen startade räknas inte som nya
    Given att bevakningen av INBOX har startat
    When ett mejl med ämnet "Offert" kommer till INBOX
    Then ska lyssnaren bara ha fått UID 4

  Scenario: Nya mejl markeras inte som lästa
    Given att bevakningen av INBOX har startat
    When ett mejl med ämnet "Offert" kommer till INBOX
    Then ska lyssnaren ha fått mejlet med UID 4 i INBOX med ämnet "Offert"
    And ska Bridge bara ha fått hämtningar med BODY.PEEK
    And ska mejlet med UID 4 fortfarande vara oläst

  Scenario: Bevakningen använder inte verktygens delade anslutning
    Given att bevakningen av INBOX har startat
    Then ska bevakningen ha en egen anslutning till Bridge
    And ska verktygens delade anslutning inte ha använts

  Scenario: IDLE förnyas innan Bridge kopplar ner den
    Given att bevakningen av INBOX har startat med förnyelse var 0.2 sekund
    When det har gått 0.9 sekunder
    Then ska Bridge ha fått minst 3 IDLE på samma anslutning
    And ska bevakningen fortfarande bevaka INBOX

  Scenario: Bevakningen återansluter när Bridge startas om och missar inga mejl
    Given att bevakningen av INBOX har startat
    When Bridge startas om och ett mejl med ämnet "Under avbrottet" kommer under tiden
    Then ska bevakningen ha återanslutit
    And ska lyssnaren ha fått mejlet med UID 4 i INBOX med ämnet "Under avbrottet"

  Scenario: Väntetiden mellan försöken fördubblas upp till taket
    Given en Bridge som inte går att nå
    When bevakningen av INBOX startas med väntetiden 1 sekund och taket 4 sekunder
    Then ska väntetiderna mellan försöken börja med 1, 2, 4, 4 sekunder

  Scenario: Nytt UIDVALIDITY nollställer vattenmärket
    Given att bevakningen av INBOX har startat
    When Bridge byter UIDVALIDITY för INBOX och numrerar om mejlen till 1 och 2
    And Bridge startas om
    Then ska bevakningen ha återanslutit
    When ett mejl med ämnet "Efter bytet" kommer till INBOX
    Then ska lyssnaren ha fått mejlet med UID 3 i INBOX med ämnet "Efter bytet"

  Scenario: Uppstarten väntar inte på en Bridge som är nere
    Given en Bridge som inte går att nå
    When bevakningen av INBOX startas
    Then ska start ha returnerat direkt
    And ska bevakningen inte bevaka INBOX just nu

  Scenario: Avstängd bevakning ansluter inte alls
    When bevakningen startas med PROTONMAIL_WATCH_ENABLED=false
    Then ska Bridge inte ha fått någon anslutning

  Scenario: stop städar alla bakgrundsuppgifter och anslutningar
    Given att INBOX och "Folders/Kunder" bevakas
    When bevakningen stoppas
    Then ska inga bevakningsuppgifter vara kvar
    And ska Bridge inte ha några öppna anslutningar

  Scenario: En lyssnare som kraschar stoppar inte bevakningen
    Given att bevakningen av INBOX har startat med en lyssnare som kastar ett fel
    When ett mejl med ämnet "Offert" kommer till INBOX
    Then ska lyssnaren ha fått mejlet med UID 4 i INBOX med ämnet "Offert"
    When ett mejl med ämnet "Nästa" kommer till INBOX
    Then ska lyssnaren ha fått mejlet med UID 5 i INBOX med ämnet "Nästa"
