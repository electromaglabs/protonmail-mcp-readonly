Feature: Keynote-presentationer (.key) kan bifogas
  Som användare som skickar presentationer från min Mac
  vill jag kunna bifoga Keynote-filer, som också slutar på .key,
  utan att spärren mot privata nycklar slår till i onödan
  — men en riktig privat nyckel ska fortfarande stoppas.

  Scenario: En Keynote-presentation bifogas
    Given bilagekatalogen har en Keynote-presentation "Kvartal.key"
    When filen "Kvartal.key" görs till bilaga
    Then ska bilagan "Kvartal.key" skapas

  Scenario: En privat nyckel med ändelsen .key stoppas
    Given bilagekatalogen har en privat nyckel "server.key"
    When filen "server.key" görs till bilaga
    Then ska bilagan vägras med ett fel som nämner "hemligheter"

  Scenario: En .key-fil som inte är en Keynote-presentation stoppas
    Given bilagekatalogen har textfilen "okand.key" med innehållet "abc123"
    When filen "okand.key" görs till bilaga
    Then ska bilagan vägras med ett fel som nämner "hemligheter"

  Scenario: En zip-fil med ändelsen .key som innehåller en privat nyckel stoppas
    Given bilagekatalogen har en Keynote-liknande fil "lurig.key" som innehåller en privat nyckel
    When filen "lurig.key" görs till bilaga
    Then ska bilagan vägras med ett fel som nämner "privat nyckel"

  Scenario: Andra hemliga namn stoppas även om filen ser ut som en Keynote-presentation
    Given bilagekatalogen har en Keynote-presentation "id_rsa.key"
    When filen "id_rsa.key" görs till bilaga
    Then ska bilagan vägras med ett fel som nämner "hemligheter"
