Feature: Sökningar med många träffar låser inte servern
  Som en MCP-klient
  vill jag kunna söka i en mapp med tusentals träffar
  utan att ett jättelikt FETCH-svar kraschar IMAP-tolkningen och låser servern.

  Scenario: Metadata hämtas i delar
    Given att en sökning träffar 450 brev
    And att metadata hämtas högst 200 brev åt gången
    When jag söker med max_results 200
    Then ska jag få de 200 nyaste träffarna
    And ska inget FETCH-kommando ha gällt fler än 200 brev

  Scenario: Antalet träffar har ett tak som syns i verktygets schema
    When jag läser schemat för search_emails
    Then ska max_results ha standardvärdet 50 och vara begränsat till 1–200

  Scenario: För stort max_results avvisas
    Given att en sökning träffar 450 brev
    When jag anropar search_emails med max_results 3000
    Then ska anropet avvisas utan att något hämtas
