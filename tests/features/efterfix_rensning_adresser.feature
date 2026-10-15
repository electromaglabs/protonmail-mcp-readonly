Feature: Adressen som visas är adressen som svaret går till
  Som användare av en LLM som läser och besvarar min e-post
  vill jag att en adress aldrig ändras när den visas, bara flaggas om den innehåller osynliga tecken,
  och att text som bara ser ut som en adress i ett visningsnamn rensas som vanlig text
  så att det jag ser är exakt den mottagare som ett svar skulle gå till.

  Scenario: Taggtecken i Reply-To lämnas i adressen och flaggas
    Given ett mejl med rubriken "Reply-To: boss<taggar>@company.com"
    When jag hämtar mejlet med get_email
    Then ska reply_to vara adressen "boss<taggar>@company.com" oförändrad
    And ska suspicious_content nämna osynliga tecken i en adress

  Scenario: Taggtecken i en adress inom vinkelparenteser lämnas och flaggas
    Given ett mejl med rubriken "Reply-To: Boss <boss@company.com<taggar>>"
    When jag hämtar mejlet med get_email
    Then ska reply_to vara adressen "Boss <boss@company.com<taggar>>" oförändrad
    And ska suspicious_content nämna osynliga tecken i en adress

  Scenario: Ett ord med snabel-a i visningsnamnet rensas som text i get_email
    Given ett mejl med rubriken "Cc: Bob<rlo>@<lro>x <b@x.se>"
    When jag hämtar mejlet med get_email
    Then ska headers "Cc" vara "Bob@x <b@x.se>"

  Scenario: Ett ord med snabel-a i visningsnamnet rensas som text i list_emails
    Given en mejllista där ett mejl har rubriken "From: secure<rlo>@<lro>paypal.com <evil@x.com>"
    When jag listar mejlen med list_emails
    Then ska from i listan vara "secure@paypal.com <evil@x.com>"

  Scenario: En adress med osynliga tecken flaggas i list_emails
    Given en mejllista där ett mejl har rubriken "From: Anna <an<zw>na@x.se>"
    When jag listar mejlen med list_emails
    Then ska from i listan vara "Anna <an<zw>na@x.se>"
    And ska raden i listan ha suspicious_content som nämner osynliga tecken i en adress

  Scenario: Ett vanligt mejl i listan har ingen suspicious_content
    Given en mejllista där ett mejl har rubriken "From: Anna Svensson <anna@x.se>"
    When jag listar mejlen med list_emails
    Then ska raden i listan sakna suspicious_content
