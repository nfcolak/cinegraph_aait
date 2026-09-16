# query.py
# SPARQL query templates for local Wikidata-like graph.

LABEL_QUERY = '''
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wd:   <http://www.wikidata.org/entity/>
SELECT ?label
WHERE {
  wd:%s rdfs:label ?label .
  FILTER (lang(?label) = "en")
}
LIMIT 1
'''


# Query by QID and relation
ONE_QID_ONE_RELATION = '''
PREFIX wd:  <http://www.wikidata.org/entity/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?obj ?label
WHERE {
  wd:%s <%s> ?obj .  # ?obj is the URI or literal we want
  OPTIONAL {
    ?obj rdfs:label ?label .
    FILTER (lang(?label) = "en")
  }
}
'''


# Query by English label (case-insensitive)
ONE_LABEL_ONE_RELATION = '''
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?obj ?label
WHERE {
  ?s rdfs:label ?l .
  FILTER (lcase(str(?l)) = lcase("%s"))  # placeholder for safe_title
  ?s <%s> ?obj .
  OPTIONAL {
    ?obj rdfs:label ?label .
    FILTER (lang(?label) = "en")
  }
}
'''
