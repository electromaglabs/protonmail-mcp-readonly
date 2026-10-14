Feature: Svara på e-post
  Som en MCP-klient som svarar på mejl
  vill jag att svaret får rätt ämne, trådning och mottagare
  så att det hamnar rätt och hänger ihop med konversationen hos mottagaren.

  Scenario Outline: Lokaliserade svarsprefix ger ett enda "Re: "
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "10" från "anna@example.se" med ämnet "<ämne>"
    When jag svarar på mejlet med UID "10" med texten "Tack!"
    Then ska svarets ämne vara "<svarsämne>"

    Examples:
      | ämne                  | svarsämne    |
      | möte                  | Re: möte     |
      | Re: möte              | Re: möte     |
      | SV: möte              | Re: möte     |
      | SV: Re: SV: möte      | Re: möte     |
      | AW: Antw: VS: möte    | Re: möte     |
      | RE[2]: möte           | Re: möte     |
      | Fwd: Fw: VB: möte     | Re: möte     |
      | Svar på frågan        | Re: Svar på frågan |
      | =?utf-8?q?SV=3A_m=C3=B6te?= | Re: möte |

  Scenario: Trådkedjan behålls även när References har annat skiftläge
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "20" med följande headers:
      """
      From: anna@example.se
      To: me@proton.me
      Subject: möte
      Message-ID: <m3@example.se>
      references: <m1@example.se> <m2@example.se>
      """
    When jag svarar på mejlet med UID "20" med texten "Tack!"
    Then ska svarets In-Reply-To vara "<m3@example.se>"
    And ska svarets References vara "<m1@example.se> <m2@example.se> <m3@example.se>"

  Scenario: Utan References används In-Reply-To som tidigare led i kedjan
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "21" med följande headers:
      """
      From: anna@example.se
      To: me@proton.me
      Subject: Re: möte
      Message-ID: <m2@example.se>
      In-Reply-To: <m1@example.se>
      """
    When jag svarar på mejlet med UID "21" med texten "Tack!"
    Then ska svarets References vara "<m1@example.se> <m2@example.se>"

  Scenario: Svaret går till Reply-To när den finns
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "30" med följande headers:
      """
      From: Utskick <noreply@lista.example.se>
      Reply-To: Diskussion <diskussion@lista.example.se>
      To: me@proton.me
      Subject: Fråga till listan
      Message-ID: <q@lista.example.se>
      """
    When jag svarar på mejlet med UID "30" med texten "Tack!"
    Then ska svaret gå till "diskussion@lista.example.se"
    And ska svaret inte ha någon kopia

  Scenario: Svara alla tar med To och Cc utom mitt eget konto och utan dubbletter
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "31" med följande headers:
      """
      From: Anna <anna@example.se>
      To: me@proton.me, Bo <bo@example.se>
      Cc: ME@Proton.me, cia@example.se, BO@example.se
      Subject: Planering
      Message-ID: <p@example.se>
      """
    When jag svarar alla på mejlet med UID "31" med texten "Låter bra"
    Then ska svaret gå till "anna@example.se, bo@example.se"
    And ska svaret ha kopia till "cia@example.se"
    And SMTP-mottagarna ska vara "anna@example.se, bo@example.se, cia@example.se"

  Scenario: Avsändare med kodat komma i namnet går att svara på
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "32" med följande headers:
      """
      From: =?utf-8?q?Svensson=2C_=C3=85sa?= <asa@example.se>
      To: me@proton.me
      Subject: Rapport
      Message-ID: <r@example.se>
      """
    When jag svarar på mejlet med UID "32" med texten "Tack!"
    Then ska svaret gå till "asa@example.se"
    And ska mottagaren "asa@example.se" heta "Svensson, Åsa" i svaret

  Scenario: Svar på ett eget skickat mejl går till originalets mottagare
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "40" i mappen "Sent" med följande headers:
      """
      From: Me <me@proton.me>
      To: Bo <bo@example.se>
      Cc: cia@example.se
      Subject: Offert
      Message-ID: <o@proton.me>
      """
    When jag svarar på mejlet med UID "40" i mappen "Sent" med texten "Påminnelse"
    Then ska svaret gå till "bo@example.se"
    And ska svaret inte ha någon kopia

  Scenario: Svara alla på ett eget skickat mejl tar med originalets kopia
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "41" i mappen "Sent" med följande headers:
      """
      From: me@proton.me
      To: bo@example.se
      Cc: cia@example.se, me@proton.me
      Subject: Offert
      Message-ID: <o2@proton.me>
      """
    When jag svarar alla på mejlet med UID "41" i mappen "Sent" med texten "Påminnelse"
    Then ska svaret gå till "bo@example.se"
    And ska svaret ha kopia till "cia@example.se"

  Scenario: Svaret citerar originalet
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "50" med följande innehåll:
      """
      From: Anna Ek <anna@example.se>
      To: me@proton.me
      Subject: Lunch
      Date: Mon, 12 Oct 2026 09:30:00 +0200
      Message-ID: <l@example.se>

      Hej!
      Ses vi imorgon?
      """
    When jag svarar på mejlet med UID "50" med texten "Ja, gärna."
    Then ska svarets brödtext börja med "Ja, gärna."
    And ska svarets brödtext innehålla "Den 2026-10-12 09:30 skrev Anna Ek:"
    And ska svarets brödtext innehålla "> Hej!"
    And ska svarets brödtext innehålla "> Ses vi imorgon?"

  Scenario: Svar med egen kopia och hemlig kopia
    Given mitt konto är "me@proton.me"
    And ett mejl med UID "51" från "anna@example.se" med ämnet "Avtal"
    When jag svarar på mejlet med UID "51" med kopia till "chef@example.se" och hemlig kopia till "arkiv@example.se"
    Then ska svaret gå till "anna@example.se"
    And ska svaret ha kopia till "chef@example.se"
    And SMTP-mottagarna ska vara "anna@example.se, chef@example.se, arkiv@example.se"
    And ska svaret sakna headern "Bcc"
