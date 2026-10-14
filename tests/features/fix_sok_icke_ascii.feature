Feature: Sökning hittar ord med åäö och ord i kodade headers
  Som svensk användare
  vill jag kunna söka på ämnen och avsändare med å, ä och ö
  så att sökningen inte tyst svarar "inga träffar" på brev som finns.

  Bakgrund: Bridge jämför SUBJECT och FROM mot de okodade headervärdena.

  Scenario: Ett ord med ä i ett Q-kodat ämne hittas
    Given att INBOX har brevet med UID "11041" och ämnet "=?utf-8?q?Svenska_Fj=C3=A4llklubben_oktober_2027?="
    And att INBOX har brevet med UID "11042" och ämnet "Något annat"
    When jag söker på ämnet "fjällklubben"
    Then ska träffarna vara UID "11041"
    And ska sökningen vara fullständig

  Scenario: Ett ASCII-ord inuti ett B-kodat ämne hittas
    Given att INBOX har brevet med UID "7" och ämnet "=?UTF-8?B?RmFrdHVyYSBmcsOlbiDDhWhsw6lucw==?="
    When jag söker på ämnet "Faktura"
    Then ska träffarna vara UID "7"

  Scenario: Ett avsändarnamn med Å hittas
    Given att INBOX har brevet med UID "8" från "=?utf-8?q?=C3=85sa_Str=C3=B6m?= <asa@example.se>"
    When jag söker på avsändaren "Åsa Ström"
    Then ska träffarna vara UID "8"

  Scenario: Svaret säger till när inte alla brev kunde kontrolleras
    Given att INBOX har 15 vanliga brev
    And att högst 10 brev kontrolleras lokalt
    When jag söker på ämnet "ä"
    Then ska sökningen inte vara fullständig
    And ska svaret förklara att since eller before kan begränsa sökningen

  Scenario: Äldre okodade träffar på ett ASCII-ord hittas fortfarande
    Given att INBOX har brevet med UID "500" och ämnet "Kvitto 2019"
    And att INBOX har 15 vanliga brev
    And att högst 10 brev kontrolleras lokalt
    When jag söker på ämnet "kvitto"
    Then ska träffarna vara UID "500"
