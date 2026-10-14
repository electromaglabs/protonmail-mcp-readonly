Feature: Brödtext och bilagor i hämtade mejl
  Som en MCP-klient
  vill jag få brödtext och bilagor som hör till rätt meddelande och i rimlig storlek
  så att svaret går att läsa och inte spräcker min kontext.

  Scenario: Stort HTML-nyhetsbrev med förvalda parametrar
    Given ett multipart/alternative-mejl med 200000 tecken HTML
    When jag hämtar mejlet med get_email med förvalda parametrar
    Then ska body_html vara högst 600 tecken
    And body_plain ska vara högst 600 tecken

  Scenario: Hela HTML:en går att få med body_format full
    Given ett multipart/alternative-mejl med 200000 tecken HTML
    When jag hämtar mejlet med get_email och body_format "full"
    Then ska body_html vara minst 200000 tecken
