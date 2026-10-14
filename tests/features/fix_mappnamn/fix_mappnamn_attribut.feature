Feature: Mapparnas typ, valbarhet och special-use
  Som en MCP-klient
  vill jag veta vilka mappar som är systemmappar, mappar, etiketter eller behållare
  och vilka som går att öppna
  för att inte läsa en behållare som om den vore en tom mapp.

  Scenario: Systemmappar får typen system och sin special-use
    Given att Bridge listar mappen "INBOX" med attributen "\Noinferiors \Unmarked"
    And att Bridge listar mappen "Drafts" med attributen "\Drafts \Noinferiors \Unmarked"
    And att Bridge listar mappen "Starred" med attributen "\Flagged \Noinferiors \Unmarked"
    And att Bridge listar mappen "All Mail" med attributen "\All \Noinferiors \Unmarked"
    And att Bridge listar mappen "Spam" med attributen "\Junk \Noinferiors \Unmarked"
    When jag listar mapparna
    Then ska mappen "INBOX" vara av typen "system"
    And ska mappen "INBOX" sakna special-use
    And ska mappen "Drafts" vara av typen "system"
    And ska mappen "Drafts" ha special-use "\Drafts"
    And ska mappen "Starred" ha special-use "\Flagged"
    And ska mappen "All Mail" ha special-use "\All"
    And ska mappen "Spam" ha special-use "\Junk"
    And ska alla dessa mappar gå att välja

  Scenario: Folders och Labels är behållare som inte går att välja
    Given att Bridge listar mappen "Folders" med attributen "\Noselect \Unmarked"
    And att Bridge listar mappen "Labels" med attributen "\Noselect \Unmarked"
    When jag listar mapparna
    Then ska mappen "Folders" vara av typen "container"
    And ska mappen "Folders" inte gå att välja
    And ska mappen "Labels" vara av typen "container"
    And ska mappen "Labels" inte gå att välja

  Scenario: Pseudo-förälder till en etikett med snedstreck är en behållare
    Given att Bridge listar mappen "Labels/Neomeda\\" med attributen "\Noselect"
    And att Bridge listar mappen "Labels/Neomeda\\/Kvitto\\/Faktura" med attributen "\Unmarked"
    When jag listar mapparna
    Then ska mappen "Labels/Neomeda\" vara av typen "container"
    And ska mappen "Labels/Neomeda\" inte gå att välja
    And ska mappen "Labels/Neomeda\/Kvitto\/Faktura" vara av typen "label"

  Scenario: Egna mappar och etiketter
    Given att Bridge listar mappen "Folders/Jobb" med attributen "\Marked"
    And att Bridge listar mappen "Labels/N&AOQ-s Samf&AOQ-llighet" med attributen "\Unmarked"
    When jag listar mapparna
    Then ska mappen "Folders/Jobb" vara av typen "folder"
    And ska mappen "Labels/Näs Samfällighet" vara av typen "label"
    And ska alla dessa mappar gå att välja
