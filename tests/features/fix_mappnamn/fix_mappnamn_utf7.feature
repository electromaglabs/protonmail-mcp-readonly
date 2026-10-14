Feature: Mappnamn med å, ä, ö och andra tecken utanför ASCII
  Som en MCP-klient
  vill jag se och använda mappnamnen som de heter i Proton
  eftersom Bridge skickar dem i modified UTF-7 (RFC 3501 §5.1.3).

  Scenario: Mappnamn med svenska tecken visas läsbart
    Given att Bridge listar mappen "Labels/N&AOQ-s Samf&AOQ-llighet"
    When jag listar mapparna
    Then ska mappen "Labels/Näs Samfällighet" finnas i listan

  Scenario: Läsbart namn kodas innan det skickas till Bridge
    When jag hämtar status för "Labels/Grönvik"
    Then ska Bridge ha fått mappnamnet "Labels/Gr&APY-nvik"

  Scenario: Et-tecken i namnet kodas som "&-"
    When jag hämtar status för "Folders/R&D"
    Then ska Bridge ha fått mappnamnet "Folders/R&-D"

  Scenario: Varje listat namn går att skicka tillbaka oförändrat
    Given att Bridge listar mappen "INBOX"
    And att Bridge listar mappen "Labels/Sl&AOQ-ktforskning"
    And att Bridge listar mappen "Folders/R&-D"
    And att Bridge listar mappen "Labels/&2D3eAA- Fest"
    And att Bridge listar mappen "Labels/Sm&APY-r\\/Br&APY-d"
    When jag listar mapparna
    And jag hämtar status för varje listad mapp
    Then ska Bridge ha fått tillbaka exakt de namn som listades
