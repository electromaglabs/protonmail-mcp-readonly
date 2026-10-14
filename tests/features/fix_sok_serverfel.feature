Feature: Serverfel vid sökning syns som fel
  Som en MCP-klient
  vill jag få serverns felmeddelande när en sökning misslyckas
  i stället för en tom lista som ser ut som "inga träffar".

  Scenario: Servern avvisar sökkommandot
    Given att servern svarar "BAD" med texten "[Error offset=35]: expected - after year" på SEARCH
    When jag söker efter olästa brev i INBOX
    Then ska sökningen misslyckas med ett fel som innehåller "expected - after year"

  Scenario: Servern vägrar sökningen
    Given att servern svarar "NO" med texten "mailbox is busy" på SEARCH
    When jag söker efter olästa brev i INBOX
    Then ska sökningen misslyckas med ett fel som innehåller "mailbox is busy"

  Scenario: Servern vägrar hämta metadata för träffarna
    Given att SEARCH träffar brev 1 och 2
    And att servern svarar "NO" med texten "fetch failed" på FETCH
    When jag söker efter olästa brev i INBOX
    Then ska sökningen misslyckas med ett fel som innehåller "fetch failed"

  Scenario: En sökning utan träffar är fortfarande ett tomt resultat
    Given att SEARCH inte träffar något
    When jag söker efter olästa brev i INBOX
    Then ska resultatet vara tomt
