Feature: Etiketter med snedstreck i namnet
  Som en MCP-klient
  vill jag kunna nå etiketter som har "/" i namnet
  eftersom Bridge escapar snedstrecket med ett backslash i mappnamnet.

  Scenario: Etikettnamnet visas utan IMAP-escapning
    Given att Bridge listar mappen "Labels/Neomeda\\/Kvitto\\/Faktura"
    When jag listar mapparna
    Then ska mappen "Labels/Neomeda\/Kvitto\/Faktura" finnas i listan

  Scenario: Etikett med snedstreck går att skicka tillbaka
    Given att Bridge listar mappen "Labels/[Superhuman]\\/AI\\/News"
    When jag listar mapparna
    And jag hämtar status för "Labels/[Superhuman]\/AI\/News"
    Then ska Bridge ha fått mappnamnet "Labels/[Superhuman]\\/AI\\/News"

  Scenario: Varje listat namn går att skicka tillbaka oförändrat
    Given att Bridge listar mappen "INBOX"
    And att Bridge listar mappen "Labels/Neomeda\\/Kvitto\\/Faktura"
    And att Bridge listar mappen "Labels/Citat \"inom\" namnet"
    When jag listar mapparna
    And jag hämtar status för varje listad mapp
    Then ska Bridge ha fått tillbaka exakt de namn som listades
