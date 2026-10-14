Feature: Skicka bilagor från bilagekatalogen
  Som MCP-klient som skickar, svarar på eller vidarebefordrar mejl
  vill jag kunna bifoga filer från bilagekatalogen
  så att mottagaren får filerna med rätt namn och typ — utan att andra filer kan läcka.

  Background:
    Given mitt konto är "me@proton.me" och bilagekatalogen innehåller "offert.pdf"

  Scenario: Ett mejl med en bilaga blir multipart/mixed med texten först
    When jag skickar ett mejl till "bob@example.se" med bilagan "offert.pdf"
    Then ska mejlet vara "multipart/mixed"
    And ska första delen vara texten
    And ska mejlet ha bilagan "offert.pdf" av typen "application/pdf" med filens innehåll

  Scenario: Ett mejl med HTML och bilaga har text och HTML före bilagan
    When jag skickar ett mejl med HTML till "bob@example.se" med bilagan "offert.pdf"
    Then ska mejlet vara "multipart/mixed"
    And ska första delen vara "multipart/alternative" med text och HTML
    And ska mejlet ha bilagan "offert.pdf" av typen "application/pdf" med filens innehåll

  Scenario: Ett filnamn med svenska tecken kodas enligt RFC 2231
    Given att bilagekatalogen också innehåller "Offert åäö.pdf"
    When jag skickar ett mejl till "bob@example.se" med bilagan "Offert åäö.pdf"
    Then ska Content-Disposition för bilagan innehålla "filename*=utf-8''Offert%20%C3%A5%C3%A4%C3%B6.pdf"
    And ska mejlet ha bilagan "Offert åäö.pdf" av typen "application/pdf" med filens innehåll

  Scenario: En fil med okänd filändelse skickas som application/octet-stream
    Given att bilagekatalogen också innehåller "data.okand"
    When jag skickar ett mejl till "bob@example.se" med bilagan "data.okand"
    Then ska mejlet ha bilagan "data.okand" av typen "application/octet-stream" med filens innehåll

  Scenario: En fil utanför bilagekatalogen skickas inte
    Given en fil "hemlig.txt" utanför bilagekatalogen
    When jag skickar ett mejl till "bob@example.se" med bilagan "../utanfor/hemlig.txt"
    Then ska sändningen avvisas med ett fel som nämner "bilagekatalogen"
    And inget mejl ska ha skickats

  Scenario: Fler än 20 bilagor avvisas
    When jag skickar ett mejl till "bob@example.se" med bilagan "offert.pdf" 21 gånger
    Then ska sändningen avvisas med ett fel som nämner "högst 20"
    And inget mejl ska ha skickats

  Scenario: Bilagor över 25 MB tillsammans avvisas
    Given att bilagekatalogen också innehåller "stor1.bin" och "stor2.bin" på 13 MB vardera
    When jag skickar ett mejl till "bob@example.se" med bilagorna "stor1.bin" och "stor2.bin"
    Then ska sändningen avvisas med ett fel som nämner "25 MB"
    And inget mejl ska ha skickats

  Scenario: Ett svar kan ha en bilaga
    Given ett mejl med UID "5" i "INBOX" från "anna@example.se"
    When jag svarar på mejlet "5" i "INBOX" med bilagan "offert.pdf"
    Then ska svaret gå till "anna@example.se" med In-Reply-To satt
    And ska mejlet ha bilagan "offert.pdf" av typen "application/pdf" med filens innehåll

  Scenario: Ett svar med en fil utanför bilagekatalogen skickas inte
    Given ett mejl med UID "5" i "INBOX" från "anna@example.se"
    And en fil "hemlig.txt" utanför bilagekatalogen
    When jag svarar på mejlet "5" i "INBOX" med bilagan "../utanfor/hemlig.txt"
    Then ska sändningen avvisas med ett fel som nämner "bilagekatalogen"
    And inget mejl ska ha skickats

  Scenario: En vidarebefordran behåller originalets bilagor och får den nya
    Given ett mejl med UID "6" i "INBOX" från "anna@example.se" med bilagan "faktura.pdf"
    When jag vidarebefordrar mejlet "6" i "INBOX" till "bob@example.se" med bilagan "offert.pdf"
    Then ska mejlet ha bilagan "faktura.pdf" av typen "application/pdf"
    And ska mejlet ha bilagan "offert.pdf" av typen "application/pdf" med filens innehåll
