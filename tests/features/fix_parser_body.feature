Feature: Brödtext och bilagor i hämtade mejl
  Som en MCP-klient
  vill jag få brödtext och bilagor som hör till rätt meddelande och i rimlig storlek
  så att svaret går att läsa och inte spräcker min kontext.

  Scenario: Stort HTML-nyhetsbrev med förvalda parametrar
    Given ett multipart/alternative-mejl med 200000 tecken HTML
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then ska body_html saknas
    And body_plain ska vara högst 600 tecken

  Scenario: Hela HTML:en går att få med body_format full
    Given ett multipart/alternative-mejl med 200000 tecken HTML
    When jag hämtar mejlet med get_email och body_format "full"
    Then ska body_html vara minst 200000 tecken

  Scenario: Vidarebefordrat mejl blandas inte in i ytterbrevet
    Given ett HTML-mejl med ett bifogat vidarebefordrat mejl som har en egen bilaga
    When jag hämtar mejlet med get_email och body_format "full"
    Then ska body_plain inte innehålla "Inre text"
    And body_html ska innehålla "Yttre text"
    And bilagorna ska vara exakt "message/rfc822"

  Scenario: Bilaga märkt inline med filnamn listas som bilaga
    Given ett mejl med brödtexten "Se fakturan" och en PDF märkt "inline; filename=\"faktura.pdf\""
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then ska bilagornas filnamn vara "faktura.pdf"
    And body_plain ska innehålla "Se fakturan"

  Scenario: Bilaga med versaler i dispositionen tar inte över brödtexten
    Given ett mejl med brödtexten "Riktig text" och en textbilaga märkt "ATTACHMENT; filename=\"logg.txt\""
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then ska bilagornas filnamn vara "logg.txt"
    And body_plain ska innehålla "Riktig text"
    And body_plain ska inte innehålla "loggrad"

  Scenario: Mejl som bara består av en PDF från en skanner
    Given ett mejl som bara är en PDF
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then ska body_plain vara tom
    And bilagorna ska vara exakt "application/pdf"

  Scenario: HTML uppdelad runt en inline-bild (Apple Mail)
    Given ett multipart/mixed-mejl med HTML-delarna "Del 1" och "Del 2" runt en bild
    When jag hämtar mejlet med get_email och body_format "full"
    Then ska body_html innehålla "Del 1"
    And body_html ska innehålla "Del 2"

  Scenario: HTML-brev utan textdel blir läsbar text
    Given ett HTML-mejl utan textdel med stilmall, entiteter och stycken
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then body_plain ska innehålla "Hej & välkommen"
    And body_plain ska inte innehålla "color"
    And body_plain ska inte innehålla "&amp;"
    And "Rad 1" och "Rad 2" ska stå på olika rader i body_plain

  Scenario: Citat i ett HTML-svar tas bort i stripped-läget
    Given ett HTML-mejl utan textdel med svaret "Mitt svar" och citatet "Gammal text"
    When jag hämtar mejlet med get_email och body_format "stripped"
    Then body_plain ska innehålla "Mitt svar"
    And body_plain ska inte innehålla "Gammal text"

  Scenario: Utskick med en tom textdel och riktig HTML
    Given ett multipart/alternative-mejl med textdelen " " och HTML-delen "<p>Riktigt innehåll</p>"
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then body_plain ska innehålla "Riktigt innehåll"

  Scenario: Okänt body_format ger ett tydligt fel
    Given ett multipart/alternative-mejl med 2000 tecken HTML
    When jag försöker hämta mejlet med body_format "html"
    Then ska anropet avvisas med ett fel som nämner "body_format"

  Scenario: Negativ max_length ger ett tydligt fel
    Given ett multipart/alternative-mejl med 2000 tecken HTML
    When jag försöker hämta mejlet med max_length -5
    Then ska anropet avvisas med ett fel som nämner "max_length"

  Scenario: En avskiljarrad "--" kapar inte resten av texten i stripped-läget
    Given ett textmejl med raderna "Agenda", "--" och "punkt 1"
    When jag hämtar mejlet med get_email och body_format "stripped"
    Then body_plain ska innehålla "punkt 1"

  Scenario: Signaturen efter "-- " tas bort i stripped-läget
    Given ett textmejl med raderna "Hej", "-- " och "Anna Andersson"
    When jag hämtar mejlet med get_email och body_format "stripped"
    Then body_plain ska innehålla "Hej"
    And body_plain ska inte innehålla "Anna Andersson"
